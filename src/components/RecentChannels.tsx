import { PanelSectionRow, ButtonItem } from "@decky/ui";
import { RecentChannel } from "../../vencordBridge/types";

interface RecentChannelsProps {
    recents: RecentChannel[];
    currentChannelId?: string | null;
    isActionPending?: boolean;
    onJoinRecent: (recent: RecentChannel) => void;
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
    mutedText: {
        fontSize: "12px",
        color: "#8e9297",
    } as const,
};

export function RecentChannels({
    recents,
    currentChannelId,
    isActionPending,
    onJoinRecent,
}: RecentChannelsProps) {
    if (!recents || recents.length === 0) return null;

    return (
        <>
            <PanelSectionRow>
                <div style={{ ...S.sectionLabel, marginTop: "4px" }}>Recent Channels</div>
            </PanelSectionRow>

            {recents.map((item) => {
                const isActive = currentChannelId === item.channel_id;

                return (
                    <PanelSectionRow key={`recent-${item.guild_id}-${item.channel_id}`}>
                        <div style={S.fullWidth}>
                            <ButtonItem
                                layout="below"
                                onClick={() => onJoinRecent(item)}
                                disabled={isActionPending || isActive}
                            >
                                <div style={S.fullWidth}>
                                    <div style={S.truncate}>
                                        {isActive ? "✓ " : ""}{item.channel_name}
                                    </div>
                                    <div style={{ fontSize: "11px", color: "#8e9297", marginTop: "1px", ...S.truncate }}>
                                        {item.guild_name}
                                    </div>
                                </div>
                            </ButtonItem>
                        </div>
                    </PanelSectionRow>
                );
            })}
        </>
    );
}
