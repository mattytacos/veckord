/**
 * Veckord Local Bridge Protocol Definitions & Validators.
 * 
 * Shared framing, validation, and error code definitions for the local Unix socket bridge.
 */

export const PROTOCOL_VERSION = 1;
export const MAX_REQUEST_SIZE = 64 * 1024; // 64 KB

export enum BridgeErrorCode {
    INVALID_JSON = "INVALID_JSON",
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION",
    MISSING_ID = "MISSING_ID",
    UNKNOWN_METHOD = "UNKNOWN_METHOD",
    INVALID_PARAMS = "INVALID_PARAMS",
    DUPLICATE_ID = "DUPLICATE_ID",
    DUPLICATE_REQUEST_ID = "DUPLICATE_REQUEST_ID",
    OVERSIZED_REQUEST = "OVERSIZED_REQUEST",
    ADAPTER_ERROR = "ADAPTER_ERROR",
    TIMEOUT = "TIMEOUT",
    RENDERER_UNAVAILABLE = "RENDERER_UNAVAILABLE",
    RENDERER_TIMEOUT = "RENDERER_TIMEOUT",
    QUEUE_FULL = "QUEUE_FULL",
    PLUGIN_STOPPING = "PLUGIN_STOPPING",
    INTERNAL_ERROR = "INTERNAL_ERROR",
}

export interface BridgeRequest {
    version: number;
    id: string;
    method: string;
    params?: Record<string, any>;
}

export interface QueuedBridgeRequest {
    id: string;
    method: string;
    params: Record<string, any>;
}

export interface BridgeErrorPayload {
    code: BridgeErrorCode | string;
    message: string;
}

export interface BridgeSuccessResponse {
    version: number;
    id: string;
    ok: true;
    result: any;
}

export interface BridgeErrorResponse {
    version: number;
    id: string;
    ok: false;
    error: BridgeErrorPayload;
}

export type BridgeResponse = BridgeSuccessResponse | BridgeErrorResponse;

export const ALLOWED_METHODS = new Set([
    "ping",
    "getRendererProof",
    "renderer-proof",
    "getRendererDiagnostics",
    "diagnostics",
    "getStatus",
    "getGuilds",
    "getVoiceChannels",
    "getCurrentVoiceChannel",
    "getVoiceSettings",
    "joinVoiceChannel",
    "leaveVoiceChannel",
    "setMuted",
    "setDeafened",
]);

/**
 * Validate raw incoming request object.
 */
export function validateBridgeRequest(data: any): { valid: true; request: BridgeRequest } | { valid: false; error: BridgeErrorPayload } {
    if (!data || typeof data !== "object") {
        return { valid: false, error: { code: BridgeErrorCode.INVALID_JSON, message: "Request must be a JSON object" } };
    }

    if (typeof data.id !== "string" || !data.id.trim()) {
        return { valid: false, error: { code: BridgeErrorCode.MISSING_ID, message: "Request missing non-empty 'id' string" } };
    }

    if (typeof data.version !== "number" || data.version !== PROTOCOL_VERSION) {
        return { valid: false, error: { code: BridgeErrorCode.UNSUPPORTED_VERSION, message: `Unsupported protocol version ${data.version}, expected ${PROTOCOL_VERSION}` } };
    }

    if (typeof data.method !== "string" || !ALLOWED_METHODS.has(data.method)) {
        return { valid: false, error: { code: BridgeErrorCode.UNKNOWN_METHOD, message: `Unknown or disallowed method '${data.method}'` } };
    }

    // Parameter type validation
    const params = data.params || {};
    if (typeof params !== "object" || Array.isArray(params)) {
        return { valid: false, error: { code: BridgeErrorCode.INVALID_PARAMS, message: "'params' must be an object" } };
    }

    switch (data.method) {
        case "getVoiceChannels":
            if (typeof params.guildId !== "string" || !params.guildId.trim()) {
                return { valid: false, error: { code: BridgeErrorCode.INVALID_PARAMS, message: "Method 'getVoiceChannels' requires non-empty string param 'guildId'" } };
            }
            break;
        case "joinVoiceChannel":
            if (typeof params.channelId !== "string" || !params.channelId.trim()) {
                return { valid: false, error: { code: BridgeErrorCode.INVALID_PARAMS, message: "Method 'joinVoiceChannel' requires non-empty string param 'channelId'" } };
            }
            break;
        case "setMuted":
            if (typeof params.muted !== "boolean") {
                return { valid: false, error: { code: BridgeErrorCode.INVALID_PARAMS, message: "Method 'setMuted' requires boolean param 'muted'" } };
            }
            break;
        case "setDeafened":
            if (typeof params.deafened !== "boolean") {
                return { valid: false, error: { code: BridgeErrorCode.INVALID_PARAMS, message: "Method 'setDeafened' requires boolean param 'deafened'" } };
            }
            break;
    }

    return {
        valid: true,
        request: {
            version: data.version,
            id: data.id,
            method: data.method,
            params: params,
        },
    };
}

export function buildSuccessResponse(id: string, result: any): BridgeSuccessResponse {
    return {
        version: PROTOCOL_VERSION,
        id: id,
        ok: true,
        result: result !== undefined ? result : {},
    };
}

export function buildErrorResponse(id: string, code: BridgeErrorCode | string, message: string): BridgeErrorResponse {
    return {
        version: PROTOCOL_VERSION,
        id: id,
        ok: false,
        error: {
            code: code,
            message: message,
        },
    };
}
