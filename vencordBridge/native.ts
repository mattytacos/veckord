/**
 * Deckord Vencord Native Bridge Server.
 * 
 * Runs in Vesktop's Node.js main process context.
 * Creates an authenticated Unix domain socket and manages a renderer-pull
 * long-polling request queue with bounded capacity and timeouts.
 */

import * as fs from "fs";
import * as path from "path";
import * as net from "net";

import {
    PROTOCOL_VERSION,
    MAX_REQUEST_SIZE,
    BridgeErrorCode,
    BridgeRequest,
    QueuedBridgeRequest,
    BridgeResponse,
    validateBridgeRequest,
    buildSuccessResponse,
    buildErrorResponse,
} from "./bridgeProtocol";

export interface BridgeStartResult {
    ok: boolean;
    socketPath: string;
    runtimeDir: string;
    errorCode?: string;
    errorMessage?: string;
}

// Bounded configuration limits
const MAX_QUEUED_REQUESTS = 32;
const MAX_IN_FLIGHT_REQUESTS = 8;
const RENDERER_RESPONSE_TIMEOUT_MS = 10000; // 10 seconds
const RENDERER_HEARTBEAT_EXPIRY_MS = 30000;  // 30 seconds
const LONG_POLL_DURATION_MS = 15000;         // 15 seconds

interface InFlightEntry {
    request: BridgeRequest;
    socket: net.Socket;
    instanceId: string;
    timestamp: number;
    timer: any;
    resolve: (resp: BridgeResponse) => void;
}

interface QueuedEntry {
    request: BridgeRequest;
    socket: net.Socket;
    timestamp: number;
    timer: any;
    resolve: (resp: BridgeResponse) => void;
}

// Active renderer tracking
let activeRendererInstanceId: string | null = null;
let lastRendererHeartbeat: number = 0;
let isPluginStopping: boolean = false;

// Request queues and maps
const queuedRequests: QueuedEntry[] = [];
const inFlightRequests: Map<string, InFlightEntry> = new Map();
const activeRequestIds: Set<string> = new Set();
const longPollWaiters: Array<{
    instanceId: string;
    resolve: (req: QueuedBridgeRequest | null) => void;
    timer: any;
}> = [];

export class DeckordNativeBridgeServer {
    private server: net.Server | null = null;
    private activeSockets: Set<net.Socket> = new Set();
    public socketPath: string = "";

    constructor(socketPathOverride?: string) {
        this.socketPath = socketPathOverride || this.resolveSocketPath();
    }

    public resolveSocketPath(): string {
        const xdgRuntime = process.env["XDG_RUNTIME_DIR"] || `/run/user/${typeof process.getuid === "function" ? process.getuid() : 1000}`;
        return path.join(xdgRuntime, "deckord", "bridge.sock");
    }

    public async start(): Promise<string> {
        isPluginStopping = false;
        const parentDir = path.dirname(this.socketPath);
        const uid = typeof process.getuid === "function" ? process.getuid() : 1000;

        if (!fs.existsSync(parentDir)) {
            fs.mkdirSync(parentDir, { mode: 0o700, recursive: true });
        } else {
            try {
                fs.chmodSync(parentDir, 0o700);
            } catch (e) {}
        }

        if (fs.existsSync(this.socketPath)) {
            const stat = fs.lstatSync(this.socketPath);
            if (stat.isSocket()) {
                if (typeof stat.uid === "number" && stat.uid === uid) {
                    fs.unlinkSync(this.socketPath);
                }
            }
        }

        return new Promise((resolve, reject) => {
            this.server = net.createServer((socket) => this.handleConnection(socket));

            this.server.on("error", (err) => {
                console.error("[DeckordNative] Socket server error:", err);
                reject(err);
            });

            this.server.listen(this.socketPath, () => {
                try {
                    fs.chmodSync(this.socketPath, 0o600);
                } catch (e) {}
                console.log("[DeckordBridge] native server listening");
                console.log(`[DeckordNative] Server listening on ${this.socketPath} (mode 0600)`);
                resolve(this.socketPath);
            });
        });
    }

    private handleConnection(socket: net.Socket): void {
        this.activeSockets.add(socket);
        let buffer = "";

        socket.on("data", async (chunk: Buffer) => {
            buffer += chunk.toString("utf-8");

            if (buffer.length > MAX_REQUEST_SIZE && !buffer.includes("\n")) {
                const errResp = buildErrorResponse("unknown", BridgeErrorCode.OVERSIZED_REQUEST, `Request exceeds maximum limit of ${MAX_REQUEST_SIZE} bytes`);
                socket.write(JSON.stringify(errResp) + "\n");
                socket.destroy();
                return;
            }

            const lines = buffer.split("\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;

                if (trimmed.length > MAX_REQUEST_SIZE) {
                    const errResp = buildErrorResponse("unknown", BridgeErrorCode.OVERSIZED_REQUEST, `Request line exceeds maximum limit of ${MAX_REQUEST_SIZE} bytes`);
                    socket.write(JSON.stringify(errResp) + "\n");
                    continue;
                }

                await this.processRequestLine(trimmed, socket);
            }
        });

        socket.on("close", () => {
            this.activeSockets.delete(socket);
            this.cleanupSocketRequests(socket);
        });

        socket.on("error", () => {
            this.activeSockets.delete(socket);
            this.cleanupSocketRequests(socket);
        });
    }

    private cleanupSocketRequests(socket: net.Socket): void {
        for (let i = queuedRequests.length - 1; i >= 0; i--) {
            if (queuedRequests[i].socket === socket) {
                const entry = queuedRequests.splice(i, 1)[0];
                if (entry.timer) clearTimeout(entry.timer);
                activeRequestIds.delete(entry.request.id);
            }
        }
    }

    private async processRequestLine(line: string, socket: net.Socket): Promise<void> {
        let rawData: any;
        try {
            rawData = JSON.parse(line);
        } catch (e: any) {
            const errResp = buildErrorResponse("unknown", BridgeErrorCode.INVALID_JSON, `Malformed JSON: ${e.message}`);
            socket.write(JSON.stringify(errResp) + "\n");
            return;
        }

        const validation = validateBridgeRequest(rawData);
        if (!validation.valid) {
            const reqId = (rawData && typeof rawData.id === "string") ? rawData.id : "unknown";
            const errResp = buildErrorResponse(reqId, validation.error.code, validation.error.message);
            socket.write(JSON.stringify(errResp) + "\n");
            return;
        }

        const req = validation.request;
        const shortId = req.id.substring(0, 8);

        if (req.method === "ping") {
            const successResp = buildSuccessResponse(req.id, { pong: true, timestamp: Date.now() });
            if (socket.writable) socket.write(JSON.stringify(successResp) + "\n");
            return;
        }

        if (isPluginStopping) {
            const errResp = buildErrorResponse(req.id, BridgeErrorCode.PLUGIN_STOPPING, "The Deckord bridge plugin is stopping");
            if (socket.writable) socket.write(JSON.stringify(errResp) + "\n");
            return;
        }

        const now = Date.now();
        const isRendererAlive = activeRendererInstanceId && (now - lastRendererHeartbeat < RENDERER_HEARTBEAT_EXPIRY_MS);
        if (!isRendererAlive) {
            const errResp = buildErrorResponse(req.id, BridgeErrorCode.RENDERER_UNAVAILABLE, "The Deckord renderer bridge is unavailable.");
            if (socket.writable) socket.write(JSON.stringify(errResp) + "\n");
            return;
        }

        if (activeRequestIds.has(req.id)) {
            const errResp = buildErrorResponse(req.id, BridgeErrorCode.DUPLICATE_REQUEST_ID, `Request ID '${req.id}' is already active`);
            if (socket.writable) socket.write(JSON.stringify(errResp) + "\n");
            return;
        }

        if (queuedRequests.length >= MAX_QUEUED_REQUESTS) {
            const errResp = buildErrorResponse(req.id, BridgeErrorCode.QUEUE_FULL, `Request queue full (limit ${MAX_QUEUED_REQUESTS})`);
            if (socket.writable) socket.write(JSON.stringify(errResp) + "\n");
            return;
        }

        activeRequestIds.add(req.id);
        console.log(`[DeckordBridge][native] host request queued: ${req.method} (${shortId})`);

        const responsePromise = new Promise<BridgeResponse>((resolve) => {
            const timer = setTimeout(() => {
                this.handleHostRequestTimeout(req.id, resolve);
            }, RENDERER_RESPONSE_TIMEOUT_MS);

            const entry: QueuedEntry = {
                request: req,
                socket: socket,
                timestamp: Date.now(),
                timer: timer,
                resolve: resolve,
            };

            queuedRequests.push(entry);
        });

        this.dispatchNextQueuedRequest();

        try {
            const resp = await responsePromise;
            if (socket.writable) {
                socket.write(JSON.stringify(resp) + "\n");
            }
        } catch (e: any) {
            const errResp = buildErrorResponse(req.id, BridgeErrorCode.INTERNAL_ERROR, e.message || "Internal error");
            if (socket.writable) {
                socket.write(JSON.stringify(errResp) + "\n");
            }
        } finally {
            activeRequestIds.delete(req.id);
        }
    }

    private handleHostRequestTimeout(reqId: string, resolve: (resp: BridgeResponse) => void): void {
        for (let i = 0; i < queuedRequests.length; i++) {
            if (queuedRequests[i].request.id === reqId) {
                queuedRequests.splice(i, 1);
                break;
            }
        }
        inFlightRequests.delete(reqId);
        activeRequestIds.delete(reqId);

        resolve(buildErrorResponse(reqId, BridgeErrorCode.RENDERER_TIMEOUT, `Renderer response timed out after ${RENDERER_RESPONSE_TIMEOUT_MS}ms`));
    }

    public dispatchNextQueuedRequest(): void {
        if (queuedRequests.length === 0 || longPollWaiters.length === 0) return;
        if (inFlightRequests.size >= MAX_IN_FLIGHT_REQUESTS) return;

        const waiter = longPollWaiters.shift()!;
        if (waiter.timer) clearTimeout(waiter.timer);

        const queued = queuedRequests.shift()!;

        inFlightRequests.set(queued.request.id, {
            request: queued.request,
            socket: queued.socket,
            instanceId: waiter.instanceId,
            timestamp: Date.now(),
            timer: queued.timer,
            resolve: queued.resolve,
        });

        const shortId = queued.request.id.substring(0, 8);
        console.log(`[DeckordBridge][native] request dispatched to renderer: ${queued.request.method} (${shortId})`);

        waiter.resolve({
            id: queued.request.id,
            method: queued.request.method,
            params: queued.request.params || {},
        });
    }

    public async stop(): Promise<void> {
        isPluginStopping = true;
        activeRendererInstanceId = null;

        for (const waiter of longPollWaiters) {
            if (waiter.timer) clearTimeout(waiter.timer);
            waiter.resolve(null);
        }
        longPollWaiters.length = 0;

        for (const entry of queuedRequests) {
            if (entry.timer) clearTimeout(entry.timer);
            entry.resolve(buildErrorResponse(entry.request.id, BridgeErrorCode.PLUGIN_STOPPING, "Plugin stopping"));
        }
        queuedRequests.length = 0;

        for (const [id, entry] of inFlightRequests.entries()) {
            if (entry.timer) clearTimeout(entry.timer);
            entry.resolve(buildErrorResponse(id, BridgeErrorCode.PLUGIN_STOPPING, "Plugin stopping"));
        }
        inFlightRequests.clear();
        activeRequestIds.clear();

        for (const sock of this.activeSockets) {
            try {
                sock.destroy();
            } catch (e) {}
        }
        this.activeSockets.clear();

        if (this.server) {
            await new Promise<void>((res) => this.server?.close(() => res()));
            this.server = null;
        }

        if (this.socketPath && fs.existsSync(this.socketPath)) {
            try {
                const stat = fs.lstatSync(this.socketPath);
                if (stat.isSocket()) {
                    fs.unlinkSync(this.socketPath);
                }
            } catch (e) {}
        }
    }
}

let globalServer: DeckordNativeBridgeServer | null = null;

// Native API Exports for VencordNative.pluginHelpers.DeckordBridge
// Note: Electron's ipcMain.handle passes event as the first parameter to every exported native function.
export async function startBridge(_?: any): Promise<BridgeStartResult> {
    const xdgRuntime = process.env["XDG_RUNTIME_DIR"] || `/run/user/${typeof process.getuid === "function" ? process.getuid() : 1000}`;
    const targetDir = path.join(xdgRuntime, "deckord");
    const socketPath = path.join(targetDir, "bridge.sock");

    console.log("[DeckordBridge] native start invoked");
    console.log(`[DeckordBridge] resolved runtime path: ${socketPath}`);

    try {
        if (!fs.existsSync(targetDir)) {
            fs.mkdirSync(targetDir, { mode: 0o700, recursive: true });
            console.log(`[DeckordBridge] directory creation result: created ${targetDir} (mode 0700)`);
        } else {
            try {
                fs.chmodSync(targetDir, 0o700);
            } catch (e) {}
            console.log(`[DeckordBridge] directory creation result: confirmed ${targetDir} (mode 0700)`);
        }

        if (fs.existsSync(socketPath)) {
            const st = fs.lstatSync(socketPath);
            if (st.isSocket()) {
                fs.unlinkSync(socketPath);
            }
        }

        if (!globalServer) {
            globalServer = new DeckordNativeBridgeServer(socketPath);
            await globalServer.start();
        }

        console.log(`[DeckordBridge] socket bind result: listening on ${socketPath} (mode 0600)`);
        return {
            ok: true,
            socketPath: socketPath,
            runtimeDir: targetDir,
        };

    } catch (e: any) {
        console.error(`[DeckordBridge] socket bind error: ${e.code || 'BIND_ERROR'} - ${e.message}`);
        return {
            ok: false,
            socketPath: socketPath,
            runtimeDir: targetDir,
            errorCode: e.code || "BIND_ERROR",
            errorMessage: e.message || String(e),
        };
    }
}

export async function stopBridge(_?: any): Promise<void> {
    if (globalServer) {
        await globalServer.stop();
        globalServer = null;
        console.log("[DeckordBridge] native stopped");
    }
}

export async function rendererHeartbeat(_: any, rendererInstanceId: string): Promise<void> {
    activeRendererInstanceId = rendererInstanceId;
    lastRendererHeartbeat = Date.now();
}

export async function waitForRequest(
    _: any,
    rendererInstanceId: string,
    timeoutMs?: number
): Promise<QueuedBridgeRequest | null> {
    if (isPluginStopping) return null;

    const requestedTimeout = typeof timeoutMs === "number" && !isNaN(timeoutMs) ? timeoutMs : LONG_POLL_DURATION_MS;

    if (activeRendererInstanceId !== rendererInstanceId) {
        activeRendererInstanceId = rendererInstanceId;
        for (let i = longPollWaiters.length - 1; i >= 0; i--) {
            if (longPollWaiters[i].instanceId !== rendererInstanceId) {
                const old = longPollWaiters.splice(i, 1)[0];
                if (old.timer) clearTimeout(old.timer);
                old.resolve(null);
            }
        }
    }
    lastRendererHeartbeat = Date.now();

    if (queuedRequests.length > 0 && inFlightRequests.size < MAX_IN_FLIGHT_REQUESTS) {
        const queued = queuedRequests.shift()!;
        inFlightRequests.set(queued.request.id, {
            request: queued.request,
            socket: queued.socket,
            instanceId: rendererInstanceId,
            timestamp: Date.now(),
            timer: queued.timer,
            resolve: queued.resolve,
        });

        const shortId = queued.request.id.substring(0, 8);
        console.log(`[DeckordBridge][native] request dispatched to renderer: ${queued.request.method} (${shortId})`);

        return {
            id: queued.request.id,
            method: queued.request.method,
            params: queued.request.params || {},
        };
    }

    const effectiveTimeout = Math.min(requestedTimeout, LONG_POLL_DURATION_MS);
    return new Promise<QueuedBridgeRequest | null>((resolve) => {
        const timer = setTimeout(() => {
            for (let i = 0; i < longPollWaiters.length; i++) {
                if (longPollWaiters[i].resolve === resolve) {
                    longPollWaiters.splice(i, 1);
                    break;
                }
            }
            resolve(null);
        }, effectiveTimeout);

        longPollWaiters.push({
            instanceId: rendererInstanceId,
            resolve: resolve,
            timer: timer,
        });
    });
}

export async function submitResponse(
    _: any,
    rendererInstanceId: string,
    response: BridgeResponse
): Promise<void> {
    if (!response || typeof response.id !== "string") {
        console.warn("[DeckordBridge][native] submitResponse received invalid response object");
        return;
    }

    lastRendererHeartbeat = Date.now();
    const shortId = response.id.substring(0, 8);
    console.log(`[DeckordBridge][native] submitResponse received: (${shortId}) from instance ${rendererInstanceId}`);

    if (activeRendererInstanceId && activeRendererInstanceId !== rendererInstanceId) {
        console.warn(`[DeckordBridge][native] Rejected response for ${shortId} from stale instance ${rendererInstanceId} (active: ${activeRendererInstanceId})`);
        return;
    }

    const entry = inFlightRequests.get(response.id);
    if (!entry) {
        console.warn(`[DeckordBridge][native] Rejected response for unknown or timed out ID: ${shortId}`);
        return;
    }

    inFlightRequests.delete(response.id);
    activeRequestIds.delete(response.id);
    if (entry.timer) clearTimeout(entry.timer);

    console.log(`[DeckordBridge][native] response matched: (${shortId})`);
    entry.resolve(response);
}
