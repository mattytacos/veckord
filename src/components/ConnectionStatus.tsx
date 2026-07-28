import { PanelSectionRow } from "@decky/ui";
import { FaDiscord } from "react-icons/fa";

export enum ConnectionState {
    CONNECTED = "Vesktop connected",
    STARTING = "Reconnecting to Vesktop…",
    BRIDGE_UNAVAILABLE = "Discord not running",
    RENDERER_UNAVAILABLE = "Not logged in",
}

export interface UserInfo {
    id: string;
    username: string;
    discriminator: string;
    avatar?: string | null;
    globalName?: string | null;
}

interface ConnectionStatusProps {
    connectionState: ConnectionState;
    currentUser: UserInfo | null;
    errorMessage: string | null;
}

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
};

export function ConnectionStatus({ connectionState, currentUser, errorMessage }: ConnectionStatusProps) {
    const connectionBadgeColor = () => {
        switch (connectionState) {
            case ConnectionState.CONNECTED: return "#43b581";
            case ConnectionState.STARTING: return "#faa61a";
            case ConnectionState.RENDERER_UNAVAILABLE: return "#f08135";
            case ConnectionState.BRIDGE_UNAVAILABLE: return "#f04747";
        }
    };

    return (
        <>
            {/* Status row */}
            <PanelSectionRow>
                <div style={{ ...S.fullWidth, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0, flex: 1 }}>
                        <FaDiscord size={18} color="#7289da" style={{ flexShrink: 0 }} />
                        <span style={S.truncate}>{connectionState}</span>
                    </div>
                    <div style={{
                        width: "10px", height: "10px", borderRadius: "50%",
                        background: connectionBadgeColor(), flexShrink: 0, marginLeft: "8px",
                    }} />
                </div>
            </PanelSectionRow>

            {currentUser && (
                <PanelSectionRow>
                    <div style={{ ...S.mutedText, ...S.truncate, ...S.fullWidth }}>
                        {currentUser.globalName ?? currentUser.username}
                    </div>
                </PanelSectionRow>
            )}

            {errorMessage && (
                <PanelSectionRow>
                    <div style={S.errorBox}>{errorMessage}</div>
                </PanelSectionRow>
            )}
        </>
    );
}
