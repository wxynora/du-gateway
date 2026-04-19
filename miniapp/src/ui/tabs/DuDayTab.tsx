import React, { useEffect, useState } from "react";
import { apiJson } from "../api";
import { useToast } from "../toast";

type DuDayEvent = {
  kind?: "routine" | "decision";
  timestamp?: string;
  time?: string;
  title?: string;
  subtitle?: string;
  actions?: string[];
  decision_label?: string;
  reason?: string;
};

type DuDayResp = {
  ok?: boolean;
  date?: string;
  items?: DuDayEvent[];
};

function normalizeEvents(input: unknown): DuDayEvent[] {
  if (!Array.isArray(input)) return [];
  return input.filter((x): x is DuDayEvent => !!x && typeof x === "object");
}

function displayDate(v: string): string {
  const raw = String(v || "").trim();
  if (!raw) return "";
  const parts = raw.split("-");
  if (parts.length !== 3) return raw;
  return `${parts[1]}.${parts[2]}`;
}

export function DuDayTab() {
  const toast = useToast();
  const [dateText, setDateText] = useState("");
  const [items, setItems] = useState<DuDayEvent[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const j = await apiJson<DuDayResp>("/miniapp-api/du-day");
        if (cancelled) return;
        setDateText(displayDate(String(j?.date || "")));
        setItems(normalizeEvents(j?.items));
      } catch (e: any) {
        if (!cancelled) toast(`读取失败：${e?.message || e}`);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [toast]);

  return (
    <div
      style={{
        backgroundColor: "#F9F7F2",
        color: "#3D3834",
        fontFamily: "'Noto Serif SC', serif",
        lineHeight: 1.7,
        overflowX: "hidden",
        paddingBottom: "100px",
        minHeight: "100%",
        position: "relative",
      }}
    >
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@300;400;500&family=Cormorant+Garamond:ital,wght@0,400;0,500;1,400&family=IBM+Plex+Mono:wght@400;500&family=Zeyada&display=swap');`}</style>

      <div
        style={{
          maxWidth: 500,
          margin: "0 auto",
          padding: "20px 20px 20px",
          position: "relative",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            marginBottom: 12,
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "0.7rem",
            color: "#7A726A",
          }}
        >
          {dateText || "--.--"}
        </div>
        <div
          style={{
            position: "absolute",
            left: 30,
            top: 28,
            bottom: 0,
            width: 1,
            background: "linear-gradient(to bottom, transparent, #7A726A 50px, #7A726A calc(100% - 50px), transparent)",
            opacity: 0.2,
          }}
        />

        {items.map((item, index) => (
          <div
            key={`${String(item.timestamp || "")}-${index}`}
            style={{
              marginBottom: 60,
              position: "relative",
              paddingLeft: 40,
            }}
          >
            <div
              style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: "0.7rem",
                color: "#7A726A",
                marginBottom: 8,
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  background: "#D4A5A5",
                  borderRadius: "50%",
                  display: "inline-block",
                  flexShrink: 0,
                }}
              />
              <span>{String(item.time || "").trim() || "--:--"}</span>
            </div>

            <div
              style={{
                background: "#fff",
                padding: 20,
                boxShadow: "0 4px 20px rgba(0,0,0,0.03)",
                borderRadius: 2,
                position: "relative",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: -10,
                  left: 20,
                  width: 40,
                  height: 15,
                  background: "rgba(232, 213, 196, 0.6)",
                  transform: "rotate(-3deg)",
                }}
              />
              <h3
                style={{
                  fontFamily: "'Zeyada', cursive",
                  fontSize: "1.3rem",
                  fontWeight: 400,
                  marginBottom: item.kind === "routine" ? 0 : 12,
                  color: "#3D3834",
                }}
              >
                {String(item.title || "").trim() || (item.kind === "decision" ? "Active Reach" : "Morning Alarm")}
              </h3>

              {item.kind === "routine" ? (
                <>
                  {item.subtitle ? (
                    <p style={{ fontSize: "0.85rem", marginTop: 8, color: "#7A726A" }}>{item.subtitle}</p>
                  ) : null}
                  <div
                    style={{
                      fontSize: "0.9rem",
                      color: "#7A726A",
                      borderTop: "1px solid #f0f0f0",
                      paddingTop: 12,
                      display: "flex",
                      gap: 12,
                      marginTop: 12,
                      flexWrap: "wrap",
                    }}
                  >
                    {(Array.isArray(item.actions) ? item.actions : []).map((action, actionIndex) => (
                      <span
                        key={`${action}-${actionIndex}`}
                        style={{
                          fontStyle: "italic",
                          fontFamily: "'Cormorant Garamond', serif",
                          fontSize: "0.75rem",
                        }}
                      >
                        {action}
                      </span>
                    ))}
                    {!Array.isArray(item.actions) || !item.actions.length ? (
                      <span
                        style={{
                          fontStyle: "italic",
                          fontFamily: "'Cormorant Garamond', serif",
                          fontSize: "0.75rem",
                        }}
                      >
                        暂无动作
                      </span>
                    ) : null}
                  </div>
                </>
              ) : null}
            </div>

            {item.kind === "decision" ? (
              <div
                style={{
                  marginTop: -15,
                  marginLeft: 20,
                  position: "relative",
                  zIndex: 5,
                }}
              >
                <div
                  style={{
                    background: "#FAF3F3",
                    padding: "16px 20px",
                    clipPath: "polygon(2% 0%, 100% 1%, 98% 100%, 0% 97%)",
                    boxShadow: "2px 2px 10px rgba(212, 165, 165, 0.1)",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "'IBM Plex Mono', monospace",
                      fontSize: "0.65rem",
                      textTransform: "uppercase",
                      color: "#D4A5A5",
                      display: "block",
                      marginBottom: 6,
                      letterSpacing: "0.1em",
                    }}
                  >
                    {String(item.decision_label || "").trim() || "渡选择了 quiet"}
                  </span>
                  <p
                    style={{
                      fontFamily: "'Cormorant Garamond', serif",
                      fontSize: "1rem",
                      lineHeight: 1.5,
                      color: "#5D544F",
                      position: "relative",
                      paddingLeft: 20,
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "'Cormorant Garamond', serif",
                        fontSize: "2.5rem",
                        color: "#D4A5A5",
                        position: "absolute",
                        left: -5,
                        top: -15,
                        opacity: 0.5,
                      }}
                    >
                      "
                    </span>
                    {String(item.reason || "").trim() || "—"}
                    <span
                      style={{
                        fontFamily: "'Cormorant Garamond', serif",
                        fontSize: "2.5rem",
                        color: "#D4A5A5",
                        position: "absolute",
                        right: -5,
                        bottom: -25,
                        opacity: 0.5,
                      }}
                    >
                      "
                    </span>
                  </p>
                </div>
              </div>
            ) : null}
          </div>
        ))}

        {!items.length ? (
          <div
            style={{
              paddingLeft: 40,
              color: "#7A726A",
              fontSize: "0.9rem",
            }}
          >
            今天还没有新的记录。
          </div>
        ) : null}
      </div>
    </div>
  );
}
