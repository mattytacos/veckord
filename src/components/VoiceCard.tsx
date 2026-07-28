import { PanelSectionRow, ButtonItem } from "@decky/ui";
import { FaMicrophone, FaMicrophoneSlash, FaVolumeUp, FaVolumeMute, FaPhoneSlash } from "react-icons/fa";

export interface VoiceChannelInfo {
    id: string;
    guildId: string;
    name: string;
    position?: number;
    userLimit?: number;
    memberCount?: number;
}

export interface VoiceSettings {
    isMuted: boolean;
    isDeafened: boolean;
    isSelfMute: boolean;
    isSelfDeaf: boolean;
}

// ── Shared styles ─────────────────────────────────────────────────────────────

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
    card: {
        width: "100%",
        boxSizing: "border-box" as const,
        background: "rgba(255,255,255,0.05)",
        borderRadius: "8px",
        padding: "10px 12px",
        border: "1px solid rgba(255,255,255,0.1)",
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
};

// ── VoiceControls ─────────────────────────────────────────────────────────────
// Mute / Deafen / Disconnect buttons — rendered only when connected.

interface VoiceControlsProps {
    currentChannel: VoiceChannelInfo | null;
    voiceSettings: VoiceSettings;
    isActionPending: boolean;
    onToggleMute: () => void;
    onToggleDeafen: () => void;
    onLeave: () => void;
}

export function VoiceControls({
    currentChannel,
    voiceSettings,
    isActionPending,
    onToggleMute,
    onToggleDeafen,
    onLeave,
}: VoiceControlsProps) {
    if (!currentChannel) return null;

    return (
        <>
            {/* Mute / Unmute */}
            <PanelSectionRow>
                <ButtonItem layout="below" onClick={onToggleMute} disabled={isActionPending}>
                    {voiceSettings.isSelfMute
                        ? <><FaMicrophone style={{ marginRight: "6px" }} />Unmute</>
                        : <><FaMicrophoneSlash style={{ marginRight: "6px" }} />Mute</>}
                </ButtonItem>
            </PanelSectionRow>

            {/* Deafen / Undeafen */}
            <PanelSectionRow>
                <ButtonItem layout="below" onClick={onToggleDeafen} disabled={isActionPending}>
                    {voiceSettings.isSelfDeaf
                        ? <><FaVolumeUp style={{ marginRight: "6px" }} />Undeafen</>
                        : <><FaVolumeMute style={{ marginRight: "6px" }} />Deafen</>}
                </ButtonItem>
            </PanelSectionRow>

            {/* Disconnect */}
            <PanelSectionRow>
                <ButtonItem layout="below" onClick={onLeave} disabled={isActionPending}>
                    <FaPhoneSlash style={{ marginRight: "6px", color: "#f04747" }} />Disconnect
                </ButtonItem>
            </PanelSectionRow>
        </>
    );
}

// ── VoiceCard ─────────────────────────────────────────────────────────────────
// VOICE CHANNEL label + connected guild/channel info card, or disconnected msg.

interface VoiceCardProps {
    currentChannel: VoiceChannelInfo | null;
    currentGuildName: string;
    voiceSettings: VoiceSettings;
}

export function VoiceCard({
    currentChannel,
    currentGuildName,
    voiceSettings,
}: VoiceCardProps) {
    return (
        <>
            <PanelSectionRow>
                <div style={S.sectionLabel}>Voice Channel</div>
            </PanelSectionRow>

            {currentChannel ? (
                <PanelSectionRow>
                    <div style={S.card}>
                        <div style={{ ...S.truncate, fontSize: "11px", color: "#8e9297" }}>
                            {currentGuildName || currentChannel.guildId}
                        </div>
                        <div style={{ ...S.truncate, fontSize: "15px", fontWeight: "bold", marginTop: "2px" }}>
                            {currentChannel.name}
                        </div>
                        <div style={{ display: "flex", gap: "6px", marginTop: "6px", flexWrap: "wrap" }}>
                            <span style={S.badge(voiceSettings.isSelfMute ? "#f04747" : "#43b581")}>
                                {voiceSettings.isSelfMute ? "Muted" : "Live"}
                            </span>
                            {voiceSettings.isSelfDeaf && (
                                <span style={S.badge("#f04747")}>Deafened</span>
                            )}
                        </div>
                    </div>
                </PanelSectionRow>
            ) : (
                <PanelSectionRow>
                    <div style={S.mutedText}>Not connected to a voice channel.</div>
                </PanelSectionRow>
            )}
        </>
    );
}
