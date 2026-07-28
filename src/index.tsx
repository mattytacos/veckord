import {
    definePlugin,
    PanelSection,
    PanelSectionRow,
    ButtonItem,
    Spinner,
    staticClasses,
} from "@decky/ui";
import { call, toaster } from "@decky/api";
import {
    FaDiscord,
    FaStar,
    FaArrowUp,
    FaArrowDown,
    FaServer,
} from "react-icons/fa";
import { useState, useEffect, useRef } from "react";

import { ConnectionStatus, ConnectionState, UserInfo } from "./components/ConnectionStatus";
import { VoiceCard, VoiceControls, VoiceChannelInfo, VoiceSettings } from "./components/VoiceCard";
import { RecentChannels } from "./components/RecentChannels";
import { AudioControls } from "./components/AudioControls";
import { AudioLevelMeters } from "./components/AudioLevelMeters";
import { RecentChannel, AudioDeviceSettings, AudioLevels } from "../vencordBridge/types";

// ─── Types ────────────────────────────────────────────────────────────────────

interface FavoriteChannel {
    guild_id: string;
    channel_id: string;
    guild_name: string;
    channel_name: string;
}

interface GuildInfo {
    id: string;
    name: string;
    channels: VoiceChannelInfo[];
}

interface BridgeStatusData {
    client?: string;
    connected?: boolean;
    user?: UserInfo | null;
    voiceSettings?: VoiceSettings;
    currentVoiceChannel?: VoiceChannelInfo | null;
}

interface ApiResponse<T = any> {
    ok: boolean;
    data?: T;
    error?: { code: string; message: string };
}

type BrowserView = "none" | "server-list" | "channel-list";

// ─── Style constants ──────────────────────────────────────────────────────────

const S = {
    fullWidth: {
        width: "100%",
        boxSizing: "border-box" as const,
        minWidth: 0,
    },
    truncate: {
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap" as const,
    },
    sectionLabel: {
        fontSize: "10px",
        fontWeight: "bold" as const,
        color: "#8e9297",
        textTransform: "uppercase" as const,
        letterSpacing: "0.6px",
        padding: "6px 0 2px",
        width: "100%",
        boxSizing: "border-box" as const,
    },
    badge: (color: string) => ({
        fontSize: "10px",
        padding: "2px 6px",
        borderRadius: "4px",
        background: color,
        color: "#fff",
        flexShrink: 0 as const,
    }),
    mutedText: {
        fontSize: "12px",
        color: "#8e9297",
    } as const,
    errorBox: {
        color: "#f04747",
        fontSize: "12px",
        background: "rgba(240,71,71,0.1)",
        padding: "6px 8px",
        borderRadius: "4px",
        width: "100%",
        boxSizing: "border-box" as const,
        wordBreak: "break-word" as const,
    },
    manageButtonWrapper: {
        marginTop: "4px",
        background: "transparent",
        border: "none",
        boxShadow: "none",
        opacity: 0.85,
    },
    manageButtonContent: {
        fontSize: "11px",
        color: "#8e9297",
        textAlign: "center" as const,
        fontWeight: "normal" as const,
        background: "transparent",
    },
    doneButtonWrapper: {
        marginTop: "4px",
        background: "transparent",
        border: "none",
        boxShadow: "none",
        opacity: 0.95,
    },
    doneButtonContent: {
        fontSize: "11px",
        color: "#dcddde",
        textAlign: "center" as const,
        fontWeight: "bold" as const,
        background: "transparent",
    },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function normalizeChannel(raw: any): VoiceChannelInfo | null {
    if (!raw || !raw.id) return null;
    return {
        id: String(raw.id),
        guildId: String(raw.guildId ?? raw.guild_id ?? ""),
        name: String(raw.name ?? "Voice Channel"),
        position: raw.position ?? 0,
        userLimit: raw.userLimit ?? raw.user_limit ?? 0,
        memberCount: raw.memberCount ?? raw.member_count ?? 0,
    };
}

const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms));

// ─── Component ────────────────────────────────────────────────────────────────

function VeckordContent() {
    // ── State ─────────────────────────────────────────────────────────────────

    const [connectionState, setConnectionState] = useState<ConnectionState>(ConnectionState.BRIDGE_UNAVAILABLE);
    const [currentUser, setCurrentUser] = useState<UserInfo | null>(null);
    const [currentChannel, setCurrentChannel] = useState<VoiceChannelInfo | null>(null);
    const [currentGuildName, setCurrentGuildName] = useState<string>("");
    const [voiceSettings, setVoiceSettings] = useState<VoiceSettings>({
        isMuted: false,
        isDeafened: false,
        isSelfMute: false,
        isSelfDeaf: false,
    });
    const [errorMessage, setErrorMessage] = useState<string | null>(null);

    const [favorites, setFavorites] = useState<FavoriteChannel[]>([]);
    const [recents, setRecents] = useState<RecentChannel[]>([]);
    const [audioSettings, setAudioSettings] = useState<AudioDeviceSettings | null>(null);
    const [audioLevels, setAudioLevels] = useState<AudioLevels | null>(null);
    const [managingFavoriteId, setManagingFavoriteId] = useState<string | null>(null);

    const [browserView, setBrowserView] = useState<BrowserView>("none");
    const [allGuilds, setAllGuilds] = useState<GuildInfo[]>([]);
    const [selectedGuild, setSelectedGuild] = useState<GuildInfo | null>(null);
    const [isBrowserLoading, setIsBrowserLoading] = useState<boolean>(false);
    const [browserError, setBrowserError] = useState<string | null>(null);

    const [isActionPending, setIsActionPending] = useState<boolean>(false);
    const [statusMessage, setStatusMessage] = useState<string>("");

    // ── Refs ──────────────────────────────────────────────────────────────────

    const pollingTimerRef = useRef<any>(null);
    const volumeDebounceTimerRef = useRef<any>(null);
    const fetchInFlightRef = useRef<boolean>(false);
    const fetchSeqRef = useRef<number>(0);

    // ── Core state fetch ──────────────────────────────────────────────────────

    const fetchState = async (guardStale = false): Promise<VoiceChannelInfo | null> => {
        if (guardStale && fetchInFlightRef.current) return null;

        fetchInFlightRef.current = true;
        const seq = ++fetchSeqRef.current;

        let parsedChannel: VoiceChannelInfo | null = null;

        try {
            const statusRes = await call<[], ApiResponse<BridgeStatusData>>("get_bridge_status");

            if (fetchSeqRef.current !== seq) return null;

            if (statusRes?.ok && statusRes.data) {
                const d = statusRes.data;

                if (d.connected && d.user) {
                    setConnectionState(ConnectionState.CONNECTED);
                    setCurrentUser(d.user);
                } else if (d.connected && !d.user) {
                    setConnectionState(ConnectionState.STARTING);
                    setCurrentUser(null);
                } else {
                    setConnectionState(ConnectionState.RENDERER_UNAVAILABLE);
                    setCurrentUser(null);
                }

                if (d.voiceSettings) setVoiceSettings(d.voiceSettings);

                parsedChannel = normalizeChannel(d.currentVoiceChannel);
                setCurrentChannel(parsedChannel);
                setErrorMessage(null);

                // Fetch audio devices and levels if connected
                if (d.connected && parsedChannel) {
                    try {
                        const audioRes = await call<[], ApiResponse<AudioDeviceSettings>>("get_audio_devices");
                        if (audioRes?.ok && audioRes.data) {
                            setAudioSettings(audioRes.data);
                        }
                    } catch {}

                    try {
                        const levelsRes = await call<[], ApiResponse<AudioLevels>>("get_audio_levels");
                        if (levelsRes?.ok && levelsRes.data) {
                            setAudioLevels(levelsRes.data);
                        }
                    } catch {}
                } else {
                    setAudioSettings(null);
                    setAudioLevels(null);
                }
            } else {
                const code = statusRes?.error?.code ?? "";
                if (code === "RENDERER_UNAVAILABLE" || code === "DISCORD_NOT_READY") {
                    setConnectionState(ConnectionState.RENDERER_UNAVAILABLE);
                } else {
                    setConnectionState(ConnectionState.BRIDGE_UNAVAILABLE);
                }
                setCurrentUser(null);
                if (code !== "" || !statusRes?.ok) {
                    setCurrentChannel(null);
                    parsedChannel = null;
                }
                if (statusRes?.error?.message) setErrorMessage(statusRes.error.message);
                setAudioSettings(null);
            }

            try {
                const favRes = await call<[], ApiResponse<{ favorites: FavoriteChannel[] }>>("get_favorite_channels");
                if (favRes?.ok && favRes.data?.favorites) {
                    setFavorites(favRes.data.favorites);
                }
            } catch {
                // Silently ignore favorites fetch failure
            }

            try {
                const recRes = await call<[], ApiResponse<{ recents: RecentChannel[] }>>("get_recent_channels");
                if (recRes?.ok && recRes.data?.recents) {
                    setRecents(recRes.data.recents);
                }
            } catch {
                // Silently ignore recents fetch failure
            }
        } catch {
            if (fetchSeqRef.current === seq) {
                setConnectionState(ConnectionState.BRIDGE_UNAVAILABLE);
                setErrorMessage("Lost connection to Vesktop");
            }
        } finally {
            if (fetchSeqRef.current === seq) {
                fetchInFlightRef.current = false;
            }
        }

        return parsedChannel;
    };

    useEffect(() => {
        fetchState();
        pollingTimerRef.current = setInterval(() => fetchState(true), 2000);
        return () => {
            if (pollingTimerRef.current) {
                clearInterval(pollingTimerRef.current);
                pollingTimerRef.current = null;
            }
        };
    }, []);

    useEffect(() => {
        if (!currentChannel) {
            setCurrentGuildName("");
            return;
        }
        const fav = favorites.find(f => f.guild_id === currentChannel.guildId);
        if (fav) {
            setCurrentGuildName(fav.guild_name);
            return;
        }
        const guild = allGuilds.find(g => g.id === currentChannel.guildId);
        setCurrentGuildName(guild?.name ?? `Guild ${currentChannel.guildId.slice(0, 6)}…`);
    }, [currentChannel, favorites, allGuilds]);

    // ── Browser fetch ──────────────────────────────────────────────────────────

    const fetchGuildsAndChannels = async () => {
        setIsBrowserLoading(true);
        setBrowserError(null);
        try {
            const res = await call<[], ApiResponse<{ guilds: GuildInfo[] }>>("get_guilds_and_channels");
            if (res?.ok && res.data?.guilds) {
                const sorted = [...res.data.guilds].sort((a, b) => a.name.localeCompare(b.name));
                setAllGuilds(sorted);
            } else {
                setBrowserError(res?.error?.message ?? "Failed to load servers");
            }
        } catch {
            setBrowserError("Failed to connect to bridge");
        } finally {
            setIsBrowserLoading(false);
        }
    };

    const openBrowser = () => {
        setBrowserView("server-list");
        fetchGuildsAndChannels();
    };

    // ── Voice action handlers ──────────────────────────────────────────────────

    const handleJoinFavorite = async (fav: FavoriteChannel) => {
        if (isActionPending) return;
        setIsActionPending(true);
        setStatusMessage(`Joining ${fav.channel_name}…`);
        try {
            const res = await call<[string, string, string, string], ApiResponse<any>>("join_voice_channel", fav.channel_id, fav.guild_id, fav.guild_name, fav.channel_name);
            if (res?.ok) {
                toaster.toast({ title: "Veckord Voice", body: `Joined ${fav.channel_name}` });

                let channel: VoiceChannelInfo | null = null;
                for (let attempt = 0; attempt < 8; attempt++) {
                    await sleep(400);
                    channel = await fetchState();
                    if (channel) break;
                }
                if (!channel) await fetchState();
            } else {
                const msg = res?.error?.message ?? "Failed to join channel";
                setErrorMessage(msg);
                toaster.toast({ title: "Veckord Error", body: msg });
            }
        } catch (e: any) {
            setErrorMessage(e?.message ?? String(e));
        } finally {
            setIsActionPending(false);
            setStatusMessage("");
        }
    };

    const handleJoinRecent = async (recent: RecentChannel) => {
        if (isActionPending) return;
        setIsActionPending(true);
        setStatusMessage(`Joining ${recent.channel_name}…`);
        try {
            const res = await call<[string, string, string, string], ApiResponse<any>>(
                "join_voice_channel", recent.channel_id, recent.guild_id, recent.guild_name, recent.channel_name
            );
            if (res?.ok) {
                toaster.toast({ title: "Veckord Voice", body: `Joined ${recent.channel_name}` });

                let channel: VoiceChannelInfo | null = null;
                for (let attempt = 0; attempt < 8; attempt++) {
                    await sleep(400);
                    channel = await fetchState();
                    if (channel) break;
                }
                if (!channel) await fetchState();
            } else {
                const msg = res?.error?.message ?? "Failed to join channel";
                setErrorMessage(msg);
                toaster.toast({ title: "Veckord Error", body: msg });
            }
        } catch (e: any) {
            setErrorMessage(e?.message ?? String(e));
        } finally {
            setIsActionPending(false);
            setStatusMessage("");
        }
    };

    const handleLeave = async () => {
        if (isActionPending) return;
        setIsActionPending(true);
        setStatusMessage("Disconnecting…");
        try {
            const res = await call<[], ApiResponse<any>>("leave_voice_channel");
            if (res?.ok) {
                toaster.toast({ title: "Veckord Voice", body: "Disconnected from voice" });
                for (let attempt = 0; attempt < 6; attempt++) {
                    await sleep(300);
                    const ch = await fetchState();
                    if (!ch) break;
                }
            } else {
                setErrorMessage(res?.error?.message ?? "Failed to disconnect");
            }
        } catch (e: any) {
            setErrorMessage(e?.message ?? String(e));
        } finally {
            setIsActionPending(false);
            setStatusMessage("");
        }
    };

    const handleToggleMute = async () => {
        if (isActionPending) return;
        setIsActionPending(true);
        const before = voiceSettings.isSelfMute;
        const next = !before;
        setStatusMessage(next ? "Muting…" : "Unmuting…");
        try {
            const res = await call<[boolean], ApiResponse<any>>("set_muted", next);
            if (res?.ok) {
                toaster.toast({ title: "Veckord Voice", body: next ? "Muted" : "Unmuted" });
                await sleep(200);
                await fetchState();
            } else {
                setErrorMessage(res?.error?.message ?? "Failed to toggle mute");
            }
        } catch (e: any) {
            setErrorMessage(e?.message ?? String(e));
        } finally {
            setIsActionPending(false);
            setStatusMessage("");
        }
    };

    const handleToggleDeafen = async () => {
        if (isActionPending) return;
        setIsActionPending(true);
        const before = voiceSettings.isSelfDeaf;
        const next = !before;
        setStatusMessage(next ? "Deafening…" : "Undeafening…");
        try {
            const res = await call<[boolean], ApiResponse<any>>("set_deafened", next);
            if (res?.ok) {
                toaster.toast({ title: "Veckord Voice", body: next ? "Deafened" : "Undeafened" });
                await sleep(200);
                await fetchState();
            } else {
                setErrorMessage(res?.error?.message ?? "Failed to toggle deafen");
            }
        } catch (e: any) {
            setErrorMessage(e?.message ?? String(e));
        } finally {
            setIsActionPending(false);
            setStatusMessage("");
        }
    };

    const handleSetAudioDevice = async (type: "input" | "output", deviceId: string) => {
        try {
            const res = await call<[string, string], ApiResponse<any>>("set_audio_device", type, deviceId);
            if (res?.ok) {
                toaster.toast({ title: "Veckord Audio", body: `Switched ${type} device` });
                await fetchState();
            }
        } catch {
            setErrorMessage(`Failed to set ${type} device`);
        }
    };

    const handleSetAudioVolume = (type: "input" | "output", volume: number) => {
        if (audioSettings) {
            setAudioSettings({
                ...audioSettings,
                inputVolume: type === "input" ? volume : audioSettings.inputVolume,
                outputVolume: type === "output" ? volume : audioSettings.outputVolume,
            });
        }

        if (volumeDebounceTimerRef.current) {
            clearTimeout(volumeDebounceTimerRef.current);
        }

        volumeDebounceTimerRef.current = setTimeout(async () => {
            try {
                await call<[string, number], ApiResponse<any>>("set_audio_volume", type, volume);
            } catch {
                setErrorMessage(`Failed to set ${type} volume`);
            }
        }, 250);
    };

    // ── Favorites management ───────────────────────────────────────────────────

    const handleAddFavorite = async (guildId: string, channelId: string, guildName: string, channelName: string) => {
        if (isActionPending) return;
        setIsActionPending(true);
        try {
            const res = await call<[string, string, string, string], ApiResponse<{ favorites: FavoriteChannel[] }>>(
                "add_favorite", guildId, channelId, guildName, channelName
            );
            if (res?.ok && res.data?.favorites) {
                setFavorites(res.data.favorites);
                toaster.toast({ title: "Favorites", body: `Added ${channelName}` });
            }
        } catch {
            setErrorMessage("Failed to add favorite");
        } finally {
            setIsActionPending(false);
        }
    };

    const handleRemoveFavorite = async (channelId: string) => {
        if (isActionPending) return;
        setIsActionPending(true);
        try {
            const res = await call<[string], ApiResponse<{ favorites: FavoriteChannel[] }>>("remove_favorite", channelId);
            if (res?.ok && res.data?.favorites) {
                setFavorites(res.data.favorites);
                setManagingFavoriteId(null);
                toaster.toast({ title: "Favorites", body: "Favorite removed" });
            }
        } catch {
            setErrorMessage("Failed to remove favorite");
        } finally {
            setIsActionPending(false);
        }
    };

    const handleMoveFavorite = async (channelId: string, direction: "up" | "down") => {
        if (isActionPending) return;
        setIsActionPending(true);
        try {
            const res = await call<[string, string], ApiResponse<{ favorites: FavoriteChannel[] }>>("move_favorite", channelId, direction);
            if (res?.ok && res.data?.favorites) setFavorites(res.data.favorites);
        } catch {
            setErrorMessage("Failed to reorder favorite");
        } finally {
            setIsActionPending(false);
        }
    };

    // ── Server-list browser view ───────────────────────────────────────────────

    if (browserView === "server-list") {
        return (
            <PanelSection title="Add Favorite — Servers">
                <PanelSectionRow>
                    <ButtonItem layout="below" onClick={() => setBrowserView("none")}>
                        ← Back to Veckord
                    </ButtonItem>
                </PanelSectionRow>

                {isBrowserLoading ? (
                    <PanelSectionRow>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                            <Spinner size={16} />
                            <span style={S.mutedText}>Loading servers…</span>
                        </div>
                    </PanelSectionRow>
                ) : browserError ? (
                    <PanelSectionRow>
                        <div style={S.errorBox}>{browserError}</div>
                    </PanelSectionRow>
                ) : allGuilds.length === 0 ? (
                    <PanelSectionRow>
                        <div style={S.mutedText}>No servers found.</div>
                    </PanelSectionRow>
                ) : (
                    allGuilds.map((g) => {
                        const favCount = favorites.filter(f => f.guild_id === g.id).length;
                        return (
                            <PanelSectionRow key={g.id}>
                                <ButtonItem
                                    layout="below"
                                    onClick={() => { setSelectedGuild(g); setBrowserView("channel-list"); }}
                                >
                                    <div style={{ ...S.fullWidth, display: "flex", alignItems: "center", gap: "8px" }}>
                                        <FaServer size={12} color="#8e9297" style={{ flexShrink: 0 }} />
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={S.truncate}>{g.name}</div>
                                            <div style={{ fontSize: "11px", color: "#8e9297", marginTop: "1px" }}>
                                                {g.channels.length} channel{g.channels.length !== 1 ? "s" : ""}
                                                {favCount > 0 && ` · ${favCount} favorited`}
                                            </div>
                                        </div>
                                    </div>
                                </ButtonItem>
                            </PanelSectionRow>
                        );
                    })
                )}
            </PanelSection>
        );
    }

    // ── Channel-list browser view ──────────────────────────────────────────────

    if (browserView === "channel-list" && selectedGuild) {
        return (
            <PanelSection title={selectedGuild.name}>
                <PanelSectionRow>
                    <ButtonItem layout="below" onClick={() => setBrowserView("server-list")}>
                        ← Back to Servers
                    </ButtonItem>
                </PanelSectionRow>

                {selectedGuild.channels.length === 0 ? (
                    <PanelSectionRow>
                        <div style={S.mutedText}>No joinable voice channels.</div>
                    </PanelSectionRow>
                ) : (
                    selectedGuild.channels.map((ch) => {
                        const isAlreadyFav = favorites.some(f => f.channel_id === ch.id);
                        return (
                            <PanelSectionRow key={ch.id}>
                                <div style={{ ...S.fullWidth, display: "flex", alignItems: "center", gap: "8px" }}>
                                    <div style={{ flex: 1, minWidth: 0, ...S.truncate }}>{ch.name}</div>
                                    {isAlreadyFav ? (
                                        <span style={{ ...S.badge("#43b581"), fontSize: "11px" }}>★ Added</span>
                                    ) : (
                                        <ButtonItem
                                            layout="below"
                                            onClick={() => handleAddFavorite(selectedGuild.id, ch.id, selectedGuild.name, ch.name)}
                                            disabled={isActionPending}
                                        >
                                            <FaStar color="#faa61a" /> Add
                                        </ButtonItem>
                                    )}
                                </div>
                            </PanelSectionRow>
                        );
                    })
                )}
            </PanelSection>
        );
    }

    // ── Main view ──────────────────────────────────────────────────────────────

    return (
        <PanelSection title="Veckord">
            <style>{`
                .veckord-manage-button,
                .veckord-manage-button button,
                .veckord-manage-button > div,
                [class*="veckord-manage-button"] {
                    background: transparent !important;
                    background-color: transparent !important;
                    border: none !important;
                    box-shadow: none !important;
                }
                .veckord-manage-button:hover,
                .veckord-manage-button:focus,
                .veckord-manage-button:focus-within,
                .veckord-manage-button.gpFocus {
                    background: rgba(255, 255, 255, 0.08) !important;
                    border-radius: 4px !important;
                }
            `}</style>

            {/* Component 1: Connection Status & User Info */}
            <ConnectionStatus
                connectionState={connectionState}
                currentUser={currentUser}
                errorMessage={errorMessage}
            />

            {/* Component 2: Voice Controls (Mute / Deafen / Disconnect) */}
            <VoiceControls
                currentChannel={currentChannel}
                voiceSettings={voiceSettings}
                isActionPending={isActionPending}
                onToggleMute={handleToggleMute}
                onToggleDeafen={handleToggleDeafen}
                onLeave={handleLeave}
            />

            {/* Component 3: Audio Controls (input/output device selectors & volume sliders) */}
            <AudioControls
                audioSettings={audioSettings}
                isConnected={connectionState === ConnectionState.CONNECTED && !!currentChannel}
                isActionPending={isActionPending}
                onSetDevice={handleSetAudioDevice}
                onSetVolume={handleSetAudioVolume}
            />

            {/* Component 4: Audio Level Meters (Mic Level & Output meters) */}
            <AudioLevelMeters
                levels={audioLevels}
                isConnected={connectionState === ConnectionState.CONNECTED && !!currentChannel}
            />

            {/* Component 5: Voice Card (VOICE CHANNEL label + channel info card) */}
            <VoiceCard
                currentChannel={currentChannel}
                currentGuildName={currentGuildName}
                voiceSettings={voiceSettings}
            />

            {/* Component 6: Recent Channels */}
            <RecentChannels
                recents={recents}
                currentChannelId={currentChannel?.id}
                isActionPending={isActionPending}
                onJoinRecent={handleJoinRecent}
            />

            {/* Favorites section */}
            <PanelSectionRow>
                <div style={{ ...S.sectionLabel, marginTop: "4px" }}>Favorites</div>
            </PanelSectionRow>

            {favorites.length === 0 ? (
                <PanelSectionRow>
                    <div style={S.mutedText}>No favorites. Browse channels below to add some.</div>
                </PanelSectionRow>
            ) : (
                favorites.map((fav, index) => {
                    const isActive = currentChannel?.id === fav.channel_id;
                    const isManaging = managingFavoriteId === fav.channel_id;

                    return (
                        <PanelSectionRow key={`${fav.guild_id}-${fav.channel_id}`}>
                            <div style={S.fullWidth}>
                                <ButtonItem
                                    layout="below"
                                    onClick={() => handleJoinFavorite(fav)}
                                    disabled={isActionPending || isActive}
                                >
                                    <div style={S.fullWidth}>
                                        <div style={S.truncate}>
                                            {isActive ? "✓ " : ""}{fav.channel_name}
                                        </div>
                                        <div style={{ fontSize: "11px", color: "#8e9297", marginTop: "1px", ...S.truncate }}>
                                            {fav.guild_name}
                                        </div>
                                    </div>
                                </ButtonItem>

                                {!isManaging ? (
                                    <div style={S.manageButtonWrapper}>
                                        <ButtonItem
                                            layout="below"
                                            onClick={() => setManagingFavoriteId(fav.channel_id)}
                                            disabled={isActionPending}
                                            {...({ className: "veckord-manage-button" } as any)}
                                        >
                                            <div style={S.manageButtonContent}>⋯ Manage</div>
                                        </ButtonItem>
                                    </div>
                                ) : (
                                    <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginTop: "4px" }}>
                                        {index > 0 && (
                                            <ButtonItem layout="below" onClick={() => handleMoveFavorite(fav.channel_id, "up")} disabled={isActionPending}>
                                                <FaArrowUp style={{ marginRight: "6px" }} />Move Up
                                            </ButtonItem>
                                        )}
                                        {index < favorites.length - 1 && (
                                            <ButtonItem layout="below" onClick={() => handleMoveFavorite(fav.channel_id, "down")} disabled={isActionPending}>
                                                <FaArrowDown style={{ marginRight: "6px" }} />Move Down
                                            </ButtonItem>
                                        )}
                                        <ButtonItem layout="below" onClick={() => handleRemoveFavorite(fav.channel_id)} disabled={isActionPending}>
                                            Remove from Favorites
                                        </ButtonItem>
                                        <div style={S.doneButtonWrapper}>
                                            <ButtonItem
                                                layout="below"
                                                onClick={() => setManagingFavoriteId(null)}
                                                {...({ className: "veckord-manage-button" } as any)}
                                            >
                                                <div style={S.doneButtonContent}>Done</div>
                                            </ButtonItem>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </PanelSectionRow>
                    );
                })
            )}

            {/* Browse button */}
            <PanelSectionRow>
                <ButtonItem
                    layout="below"
                    onClick={openBrowser}
                    disabled={isActionPending || connectionState !== ConnectionState.CONNECTED}
                >
                    Browse & Add Voice Channels
                </ButtonItem>
            </PanelSectionRow>

            {/* Pending indicator */}
            {isActionPending && (
                <PanelSectionRow>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <Spinner size={16} />
                        <span style={S.mutedText}>{statusMessage || "Processing…"}</span>
                    </div>
                </PanelSectionRow>
            )}
        </PanelSection>
    );
}

// ─── Plugin export ─────────────────────────────────────────────────────────────

export default definePlugin(() => ({
    title: <div className={staticClasses.Title}>Veckord</div>,
    icon: <FaDiscord />,
    content: <VeckordContent />,
    onDismount() {},
}));
