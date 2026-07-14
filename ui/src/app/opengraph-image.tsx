import { ImageResponse } from "next/og";

export const alt = "DocQA — ask the documents";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** OG card for links shared in chats — same archivist look: paper, ink, one stamp. */
export default function OgImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          backgroundColor: "#F7F5F0",
          color: "#22201B",
          fontFamily: "Georgia, serif",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "20px",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: "72px",
              height: "72px",
              border: "5px solid #1D4ED0",
              borderRadius: "14px",
              color: "#1D4ED0",
              fontSize: "40px",
              fontFamily: "monospace",
              fontWeight: 700,
            }}
          >
            D
          </div>
          <div style={{ fontSize: "64px", fontWeight: 600 }}>DocQA</div>
        </div>
        <div style={{ marginTop: "44px", fontSize: "44px", lineHeight: 1.3, maxWidth: "980px" }}>
          Ask questions about your documents. Get answers with page-level citations — or an
          honest &lsquo;not found&rsquo;.
        </div>
        <div
          style={{
            marginTop: "48px",
            fontSize: "24px",
            color: "#6E6A5F",
            fontFamily: "monospace",
          }}
        >
          hybrid retrieval · grounded answers · honest refusals
        </div>
      </div>
    ),
    size,
  );
}
