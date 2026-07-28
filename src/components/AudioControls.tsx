import { PanelSectionRow, Dropdown, SliderField } from "@decky/ui";
import { AudioDeviceSettings, AudioDevice } from "../../vencordBridge/types";

interface AudioControlsProps {
    audioSettings: AudioDeviceSettings | null;
    isConnected: boolean;
    isActionPending: boolean;
    onSetDevice: (type: "input" | "output", deviceId: string) => void;
    onSetVolume: (type: "input" | "output", volume: number) => void;
}

const S = {
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
    label: {
        fontSize: "12px",
        color: "#dcddde",
        marginBottom: "4px",
    },
    fullWidth: {
        width: "100%",
        boxSizing: "border-box" as const,
    },
};

export function AudioControls({
    audioSettings,
    isConnected,
    isActionPending,
    onSetDevice,
    onSetVolume,
}: AudioControlsProps) {
    if (!isConnected || !audioSettings) return null;

    const inputOptions = (audioSettings.inputDevices || []).map((d: AudioDevice) => ({
        label: d.name,
        data: d.id,
    }));
    if (inputOptions.length === 0) {
        inputOptions.push({ label: "Default Microphone", data: "default" });
    }

    const outputOptions = (audioSettings.outputDevices || []).map((d: AudioDevice) => ({
        label: d.name,
        data: d.id,
    }));
    if (outputOptions.length === 0) {
        outputOptions.push({ label: "Default Output", data: "default" });
    }

    return (
        <>
            <PanelSectionRow>
                <div style={S.sectionLabel}>Audio Devices</div>
            </PanelSectionRow>

            {/* Input Device Dropdown */}
            <PanelSectionRow>
                <div style={S.fullWidth}>
                    <div style={S.label}>Input Device</div>
                    <Dropdown
                        rgOptions={inputOptions}
                        selectedOption={audioSettings.currentInputId || "default"}
                        onChange={(opt: any) => onSetDevice("input", String(opt.data))}
                        disabled={isActionPending}
                    />
                </div>
            </PanelSectionRow>

            {/* Output Device Dropdown */}
            <PanelSectionRow>
                <div style={S.fullWidth}>
                    <div style={S.label}>Output Device</div>
                    <Dropdown
                        rgOptions={outputOptions}
                        selectedOption={audioSettings.currentOutputId || "default"}
                        onChange={(opt: any) => onSetDevice("output", String(opt.data))}
                        disabled={isActionPending}
                    />
                </div>
            </PanelSectionRow>

            <PanelSectionRow>
                <div style={S.sectionLabel}>Volume Controls</div>
            </PanelSectionRow>

            {/* Input Volume Slider */}
            <PanelSectionRow>
                <SliderField
                    label="Input Volume"
                    value={audioSettings.inputVolume ?? 100}
                    min={0}
                    max={200}
                    step={1}
                    showValue={true}
                    onChange={(val: number) => onSetVolume("input", val)}
                    disabled={isActionPending}
                />
            </PanelSectionRow>

            {/* Output Volume Slider */}
            <PanelSectionRow>
                <SliderField
                    label="Output Volume"
                    value={audioSettings.outputVolume ?? 100}
                    min={0}
                    max={200}
                    step={1}
                    showValue={true}
                    onChange={(val: number) => onSetVolume("output", val)}
                    disabled={isActionPending}
                />
            </PanelSectionRow>
        </>
    );
}
