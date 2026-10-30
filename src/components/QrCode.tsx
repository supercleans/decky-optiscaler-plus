import qrcode from "qrcode-generator";
import { useMemo } from "react";

/**
 * A QR code for a phone camera to read, drawn as an SVG on a white square.
 *
 * Medium error correction: the codes here are read off a handheld's screen,
 * at an angle and under glare, and are short enough for it to cost nothing.
 */
export function QrCode({ text, size = 180 }: Readonly<{ text: string; size?: number }>) {
  const svg = useMemo(() => {
    const code = qrcode(0, "M");
    code.addData(text);
    code.make();
    return code.createSvgTag({ cellSize: 4, margin: 4, scalable: true });
  }, [text]);
  return (
    <div
      data-qr={text}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        margin: "8px auto",
        background: "#fff",
        borderRadius: "6px",
        lineHeight: 0,
      }}
      // The library's own markup: a <svg> of rects, nothing taken from input
      // beyond the encoded text.
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
