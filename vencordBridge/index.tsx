/**
 * Veckord Voice Bridge Vencord Plugin.
 * 
 * Real Vencord plugin providing local Unix socket bridge for Veckord controller.
 * Implements a renderer-pull worker loop that long-polls native.ts for pending work.
 */

import definePlugin, { PluginNative } from "@utils/types";
import {
    UserStore,
    GuildStore,
    ChannelStore,
    VoiceStateStore,
    MediaEngineStore,
} from "@webpack/common";

import { VencordDiscordVoiceAdapter } from "./discordAdapter";
import { UserSummary, GuildSummary, VoiceChannelSummary, VoiceSettings } from "./types";

const Native = (VencordNative.pluginHelpers.VeckordBridge || VencordNative.pluginHelpers.DeckordBridge) as PluginNative<typeof import("./native")>;
const adapter = new VencordDiscordVoiceAdapter();

let isWorkerRunning: boolean = false;
let rendererInstanceId: string = "";

export default definePlugin({
    name: "VeckordBridge",
    description: "VeckordBridge build veckord-renderer-pull-v1",
    authors: [
        {
            name: "Antigravity Team",
            id: 0n,
        },
    ],

    async start() {
        rendererInstanceId = `renderer-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`;
        isWorkerRunning = true;

        console.log("[VeckordBridge] renderer plugin started");
        console.log(`[VeckordBridge] renderer instance ID: ${rendererInstanceId}`);
        console.log(`[VeckordBridge] renderer plugin start time: ${new Date().toISOString()}`);
        console.log(`[VeckordBridge] userStore resolved: ${!!UserStore}`);
        console.log(`[VeckordBridge] guildStore resolved: ${!!GuildStore}`);
        console.log(`[VeckordBridge] channelStore resolved: ${!!ChannelStore}`);
        console.log(`[VeckordBridge] voiceStateStore resolved: ${!!VoiceStateStore}`);
        console.log(`[VeckordBridge] mediaEngineStore resolved: ${!!MediaEngineStore}`);
        
        try {
            const res = await Native.startBridge();
            console.log("[VeckordBridge] startBridge result:", JSON.stringify(res));

            // Start single asynchronous renderer pull worker loop
            this.runRendererWorker(rendererInstanceId);

        } catch (e) {
            console.error("[VeckordBridge] Failed to invoke Native.startBridge:", e);
        }
    },

    async stop() {
        console.log("[VeckordBridge] renderer plugin stopped");
        isWorkerRunning = false;
        try {
            await Native.stopBridge();
        } catch (e) {
            console.error("[VeckordBridge] Failed to invoke Native.stopBridge:", e);
        }
    },

    async runRendererWorker(instanceId: string) {
        console.log(`[VeckordBridge] Renderer pull worker loop started for ${instanceId}`);

        while (isWorkerRunning && rendererInstanceId === instanceId) {
            try {
                // Long-poll native queue for up to 15 seconds
                const req = await Native.waitForRequest(instanceId, 15000);
                if (!req || !isWorkerRunning) continue;

                const { id, method, params } = req;
                const shortId = id.substring(0, 8);

                console.log(`[VeckordBridge][renderer] request pulled: ${method} (${shortId})`);

                let result: any = null;
                let ok = true;
                let errorMsg = "";

                try {
                    if (method === "getRendererProof" || method === "renderer-proof") {
                        result = {
                            rendererHandledRequest: true,
                            buildMarker: "veckord-renderer-pull-v1",
                            documentReadyState: typeof document !== "undefined" ? document.readyState : "complete",
                            documentTitlePresent: typeof document !== "undefined" && !!document.title,
                            locationProtocol: typeof location !== "undefined" ? location.protocol : "https:",
                            webpackCommonAvailable: !!(UserStore && GuildStore),
                        };
                    } else if (method === "getRendererDiagnostics" || method === "diagnostics") {
                        result = {
                            rendererLoaded: true,
                            adapterLoaded: adapter.isInitialized(),
                            nativeRequestReceived: true,
                            documentReadyState: typeof document !== "undefined" ? document.readyState : "complete",
                            userStoreResolved: !!(UserStore && typeof UserStore.getCurrentUser === "function"),
                            guildStoreResolved: !!(GuildStore && typeof GuildStore.getGuilds === "function"),
                            channelStoreResolved: !!(ChannelStore && typeof ChannelStore.getChannel === "function"),
                            voiceStateStoreResolved: !!(VoiceStateStore && typeof VoiceStateStore.getVoiceChannelId === "function"),
                            mediaEngineStoreResolved: !!(MediaEngineStore && typeof MediaEngineStore.isSelfMute === "function"),
                            currentUserAvailable: !!(UserStore && typeof UserStore.getCurrentUser === "function" && UserStore.getCurrentUser()),
                            guildCount: (GuildStore && typeof GuildStore.getGuilds === "function" && GuildStore.getGuilds()) ? Object.keys(GuildStore.getGuilds()).length : 0,
                            discordConnectionState: (UserStore && typeof UserStore.getCurrentUser === "function" && UserStore.getCurrentUser()) ? "READY" : "NOT_READY",
                        };
                    } else if (method === "getStatus") {
                        const user = adapter.getCurrentUser();
                        result = {
                            client: "Vesktop/Vencord",
                            connected: !!user,
                            user: user,
                            voiceSettings: adapter.getVoiceSettings(),
                            currentVoiceChannel: adapter.getCurrentVoiceChannel(),
                        };
                    } else if (method === "getGuilds") {
                        result = { guilds: adapter.getGuilds() };
                    } else if (method === "getVoiceChannels") {
                        result = { channels: adapter.getVoiceChannels(params?.guildId || "") };
                    } else if (method === "getCurrentVoiceChannel") {
                        result = { channel: adapter.getCurrentVoiceChannel() };
                    } else if (method === "getVoiceSettings") {
                        result = { voiceSettings: adapter.getVoiceSettings() };
                    } else if (method === "joinVoiceChannel" || method === "joinChannel") {
                        await adapter.joinVoiceChannel(params?.channelId || "", params?.guildId);
                        result = { success: true };
                    } else if (method === "leaveVoiceChannel" || method === "leaveChannel") {
                        await adapter.leaveVoiceChannel();
                        result = { success: true };
                    } else if (method === "setMuted") {
                        await adapter.setMuted(!!params?.muted);
                        result = { success: true };
                    } else if (method === "setDeafened") {
                        await adapter.setDeafened(!!params?.deafened);
                        result = { success: true };
                    } else {
                        throw new Error(`Unknown method in renderer: ${method}`);
                    }
                } catch (e: any) {
                    ok = false;
                    errorMsg = e.message || String(e);
                }

                const responsePayload: any = {
                    version: 1,
                    id: id,
                    ok: ok,
                };
                if (ok) {
                    responsePayload.result = result !== undefined ? result : {};
                } else {
                    responsePayload.error = {
                        code: "ADAPTER_ERROR",
                        message: errorMsg || "Adapter operation failed",
                    };
                }

                console.log(`[VeckordBridge][renderer] response submitted: ${method} (${shortId})`);
                await Native.submitResponse(instanceId, responsePayload);

            } catch (e) {
                console.error("[VeckordBridge] Renderer pull worker loop error:", e);
                // Pause briefly before retrying loop on error
                await new Promise((r) => setTimeout(r, 1000));
            }
        }

        console.log(`[VeckordBridge] Renderer pull worker loop finished for ${instanceId}`);
    },

    getSettingsPanel({ settings }: { settings: any }) {
        return <VeckordDiagnosticPanel />;
    },
});

/**
 * Diagnostic panel for Vencord Settings UI.
 */
function VeckordDiagnosticPanel() {
    const [user, setUser] = React.useState<UserSummary | null>(null);
    const [guilds, setGuilds] = React.useState<GuildSummary[]>([]);
    const [selectedGuildId, setSelectedGuildId] = React.useState<string>("");
    const [voiceChannels, setVoiceChannels] = React.useState<VoiceChannelSummary[]>([]);
    const [selectedChannelId, setSelectedChannelId] = React.useState<string>("");
    const [activeChannel, setActiveChannel] = React.useState<VoiceChannelSummary | null>(null);
    const [voiceSettings, setVoiceSettings] = React.useState<VoiceSettings>({
        isMuted: false,
        isDeafened: false,
        isSelfMute: false,
        isSelfDeaf: false,
    });
    const [statusMessage, setStatusMessage] = React.useState<string>("Idle");

    const refreshState = () => {
        try {
            const currentUser = adapter.getCurrentUser();
            setUser(currentUser);

            const allGuilds = adapter.getGuilds();
            setGuilds(allGuilds);

            const currentVC = adapter.getCurrentVoiceChannel();
            setActiveChannel(currentVC);

            const vSettings = adapter.getVoiceSettings();
            setVoiceSettings(vSettings);

            if (selectedGuildId) {
                const vChannels = adapter.getVoiceChannels(selectedGuildId);
                setVoiceChannels(vChannels);
            }
            setStatusMessage("State refreshed OK");
        } catch (e: any) {
            setStatusMessage(`Refresh error: ${e.message}`);
        }
    };

    React.useEffect(() => {
        refreshState();
        const interval = setInterval(refreshState, 2000);
        return () => clearInterval(interval);
    }, [selectedGuildId]);

    const handleSelectGuild = (guildId: string) => {
        setSelectedGuildId(guildId);
        const vChannels = adapter.getVoiceChannels(guildId);
        setVoiceChannels(vChannels);
        if (vChannels.length > 0) {
            setSelectedChannelId(vChannels[0].id);
        } else {
            setSelectedChannelId("");
        }
    };

    const handleJoin = async () => {
        if (!selectedChannelId) {
            setStatusMessage("Error: Select a voice channel first.");
            return;
        }
        try {
            setStatusMessage(`Joining channel ${selectedChannelId}...`);
            await adapter.joinVoiceChannel(selectedChannelId, selectedGuildId);
            setStatusMessage("Join action dispatched successfully.");
            refreshState();
        } catch (e: any) {
            setStatusMessage(`Join error: ${e.message}`);
        }
    };

    const handleLeave = async () => {
        try {
            setStatusMessage("Leaving voice channel...");
            await adapter.leaveVoiceChannel();
            setStatusMessage("Leave action dispatched successfully.");
            refreshState();
        } catch (e: any) {
            setStatusMessage(`Leave error: ${e.message}`);
        }
    };

    const handleToggleMute = async () => {
        try {
            const nextState = !voiceSettings.isSelfMute;
            setStatusMessage(`Setting mute to ${nextState}...`);
            await adapter.setMuted(nextState);
            setStatusMessage(`Mute set to ${nextState}.`);
            refreshState();
        } catch (e: any) {
            setStatusMessage(`Mute error: ${e.message}`);
        }
    };

    const handleToggleDeafen = async () => {
        try {
            const nextState = !voiceSettings.isSelfDeaf;
            setStatusMessage(`Setting deafen to ${nextState}...`);
            await adapter.setDeafened(nextState);
            setStatusMessage(`Deafen set to ${nextState}.`);
            refreshState();
        } catch (e: any) {
            setStatusMessage(`Deafen error: ${e.message}`);
        }
    };

    return (
        <div style={{ padding: "16px", color: "#f2f3f5", fontFamily: "sans-serif" }}>
            <h2 style={{ borderBottom: "1px solid #4f545c", paddingBottom: "8px" }}>
                Veckord Voice Bridge Status (Renderer Pull)
            </h2>

            {/* Current User */}
            <div style={{ margin: "12px 0", padding: "8px", background: "#2f3136", borderRadius: "4px" }}>
                <strong>Current User:</strong>{" "}
                {user ? `${user.username}#${user.discriminator} (ID: ${user.id})` : "Not Detected"}
            </div>

            {/* Voice Status */}
            <div style={{ margin: "12px 0", padding: "8px", background: "#2f3136", borderRadius: "4px" }}>
                <strong>Active Channel:</strong>{" "}
                {activeChannel ? `${activeChannel.name} (Guild: ${activeChannel.guildId})` : "None (Disconnected)"}
                <br />
                <strong>Voice State:</strong> Muted: {voiceSettings.isSelfMute ? "YES" : "NO"} | Deafened: {voiceSettings.isSelfDeaf ? "YES" : "NO"}
            </div>

            {/* Guild & Channel Selectors */}
            <div style={{ margin: "12px 0" }}>
                <label><strong>Select Server (Guild):</strong></label>
                <select
                    value={selectedGuildId}
                    onChange={(e) => handleSelectGuild(e.target.value)}
                    style={{ width: "100%", margin: "4px 0 12px 0", padding: "6px", background: "#40444b", color: "#fff" }}
                >
                    <option value="">-- Choose Guild --</option>
                    {guilds.map((g) => (
                        <option key={g.id} value={g.id}>
                            {g.name} ({g.id})
                        </option>
                    ))}
                </select>

                <label><strong>Select Voice Channel:</strong></label>
                <select
                    value={selectedChannelId}
                    onChange={(e) => setSelectedChannelId(e.target.value)}
                    style={{ width: "100%", margin: "4px 0 12px 0", padding: "6px", background: "#40444b", color: "#fff" }}
                >
                    <option value="">-- Choose Voice Channel --</option>
                    {voiceChannels.map((c) => (
                        <option key={c.id} value={c.id}>
                            {c.name} ({c.id})
                        </option>
                    ))}
                </select>
            </div>

            {/* Actions */}
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", margin: "16px 0" }}>
                <button onClick={handleJoin} style={buttonStyle("#43b581")}>
                    Join Channel
                </button>
                <button onClick={handleLeave} style={buttonStyle("#f04747")}>
                    Leave Channel
                </button>
                <button onClick={handleToggleMute} style={buttonStyle("#7289da")}>
                    {voiceSettings.isSelfMute ? "Unmute" : "Mute"}
                </button>
                <button onClick={handleToggleDeafen} style={buttonStyle("#7289da")}>
                    {voiceSettings.isSelfDeaf ? "Undeafen" : "Deafen"}
                </button>
            </div>

            {/* Status Log */}
            <div style={{ marginTop: "12px", fontSize: "12px", color: "#b9bbbe" }}>
                Status: {statusMessage}
            </div>
        </div>
    );
}

function buttonStyle(bgColor: string) {
    return {
        padding: "8px 16px",
        background: bgColor,
        color: "#ffffff",
        border: "none",
        borderRadius: "4px",
        cursor: "pointer",
        fontWeight: "bold" as const,
    };
}
