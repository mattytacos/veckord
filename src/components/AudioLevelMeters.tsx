import { PanelSectionRow } from "@decky/ui";
import { AudioLevels } from "../../vencordBridge/types";

interface AudioLevelMetersProps {
    levels: AudioLevels | null;
    isConnected: boolean;
}

const S = {
    container: {
        width: "100%",
        boxSizing: "border-box" as const,
        padding: "4px 0",
    },
    row: {
        display: "flex",
        alignItems: "center",
        gap: "8px",
        marginBottom: "4px",
    },
    label: {
        fontSize: "11px",
        color: "#8e9297",
        width: "60px",
        flexShrink: 0,
    },
    meterTrack: {
        flex: 1,
        height: "6px",
        borderRadius: "3px",
        background: "rgba(255, 255, 255, 0.1)",
        overflow: "hidden" as const,
        position: "relative" as const,
    },
    meterFill: (level: number, isSpeaking?: boolean) => ({
        height: "100%",
        width: `${Math.max(0, Math.min(100, Math.round(level * 100)))}%`,
        background: isSpeaking ? "#43b581" : "#7289da",
        borderRadius: "3px",
        transition: "width 0.1s ease-out",
    }),
};

export function AudioLevelMeters({ levels, isConnected }: AudioLevelMetersProps) {
    if (!isConnected || !levels) return null;

    return (
        <PanelSectionRow>
            <div style={S.container}>
                {/* Input Level */}
                <div style={S.row}>
                    <span style={S.label}>Mic Level</span>
                    <div style={S.meterTrack}>
                        <div style={S.meterFill(levels.inputLevel, levels.isSpeaking)} />
                    </div>
                </div>

                {/* Output Level */}
                <div style={S.row}>
                    <span style={S.label}>Output</span>
                    <div style={S.meterTrack}>
                        <div style={S.meterFill(levels.outputLevel)} />
                    </div>
                </div>
            </div>
        </PanelSectionRow>
    );
}
