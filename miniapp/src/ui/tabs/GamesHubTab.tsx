import React, { useEffect, useState } from "react";
import { apiJson } from "../api";
import { BookOpenIcon, ChevronRightIcon, RouteIconMini } from "../icons";

type WenyouStatus = {
  ok?: boolean;
  active?: boolean;
  session?: {
    instance_name?: string;
    phase?: string;
    startedAt?: string;
  } | null;
};

type PrivateBoardStatus = {
  ok?: boolean;
  state?: {
    board_size?: number;
    positions?: {
      xinyue?: number;
      du?: number;
    };
    turn_actor?: "xinyue" | "du";
    game_over?: boolean;
    theme_profile?: {
      theme?: string;
      direction_label?: string;
    };
  };
};

export function GamesHubTab({
  onOpenWenyou,
  onOpenSeseBoard,
}: {
  onOpenWenyou: () => void;
  onOpenSeseBoard: () => void;
}) {
  const [wenyouPreview, setWenyouPreview] = useState("副本大厅");
  const [boardPreview, setBoardPreview] = useState("掷骰走格");
  const [boardMeta, setBoardMeta] = useState("未开局");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [wenyou, board] = await Promise.allSettled([
        apiJson<WenyouStatus>("/miniapp-api/wenyou/status"),
        apiJson<PrivateBoardStatus>("/miniapp-api/game-tools/private_board", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command: "status", save_id: "default" }),
        }),
      ]);
      if (cancelled) return;
      if (wenyou.status === "fulfilled" && wenyou.value?.ok && wenyou.value.active && wenyou.value.session) {
        setWenyouPreview(`当前副本：${wenyou.value.session.instance_name || "系统空间进行中"}`);
      }
      if (board.status === "fulfilled" && board.value?.ok && board.value.state) {
        const state = board.value.state;
        const size = Number(state.board_size || 36);
        const me = Math.max(0, Math.min(size, Number(state.positions?.xinyue || 0)));
        const du = Math.max(0, Math.min(size, Number(state.positions?.du || 0)));
        const theme = String(state.theme_profile?.theme || "").trim();
        setBoardPreview(theme ? `${theme} · 我 ${me}/${size} · 渡 ${du}/${size}` : `我 ${me}/${size} · 渡 ${du}/${size}`);
        setBoardMeta(state.game_over ? "已结束" : state.turn_actor === "du" ? "渡行动" : "我行动");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="games-hub">
      <button className="games-card games-card-wenyou" type="button" onClick={onOpenWenyou}>
        <div className="games-card-icon games-card-icon-wenyou">
          <BookOpenIcon />
        </div>
        <div className="games-card-main">
          <div className="games-card-title-row">
            <h2>无限流</h2>
            <span>{wenyouPreview.includes("当前副本") ? "继续" : "进入"}</span>
          </div>
          <p>{wenyouPreview}</p>
        </div>
        <ChevronRightIcon />
      </button>

      <button className="games-card games-card-board" type="button" onClick={onOpenSeseBoard}>
        <div className="games-card-icon games-card-icon-board">
          <RouteIconMini className="h-6 w-6 stroke-[1.7]" />
        </div>
        <div className="games-card-main">
          <div className="games-card-title-row">
            <h2>涩涩走格棋</h2>
            <span>{boardMeta}</span>
          </div>
          <p>{boardPreview}</p>
          <div className="games-board-strip" aria-hidden="true">
            <i className="filled" />
            <i />
            <i />
            <i className="me" />
            <i />
            <i className="du" />
            <i className="finish" />
          </div>
        </div>
        <ChevronRightIcon />
      </button>

      <style>
        {`
        .games-hub {
          display: flex;
          flex-direction: column;
          gap: 12px;
          padding: 16px 2px 28px;
          font-family: "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        .games-card {
          display: flex;
          align-items: center;
          gap: 12px;
          width: 100%;
          min-height: 96px;
          border: 1px solid rgba(255, 255, 255, 0.72);
          border-radius: 24px;
          padding: 14px;
          text-align: left;
          box-shadow: 0 18px 38px rgba(109, 74, 109, 0.12);
          transition: transform 160ms ease, box-shadow 160ms ease;
        }
        .games-card:active {
          transform: scale(0.985);
          box-shadow: 0 10px 24px rgba(109, 74, 109, 0.12);
        }
        .games-card-wenyou {
          background: linear-gradient(135deg, rgba(248, 240, 244, 0.96), rgba(231, 246, 255, 0.92));
        }
        .games-card-board {
          background: linear-gradient(135deg, rgba(255, 240, 247, 0.98), rgba(232, 247, 244, 0.92));
        }
        .games-card-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 52px;
          height: 52px;
          flex: 0 0 52px;
          border-radius: 18px;
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78), 0 10px 22px rgba(104, 70, 113, 0.12);
        }
        .games-card-icon-wenyou {
          color: #704a5d;
          background: #fff8dd;
        }
        .games-card-icon-board {
          color: #884d8a;
          background: #f8bbd0;
        }
        .games-card-main {
          min-width: 0;
          flex: 1;
        }
        .games-card-title-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
        }
        .games-card h2 {
          margin: 0;
          color: #3d3043;
          font-size: 17px;
          font-weight: 800;
          line-height: 1.2;
        }
        .games-card-title-row span {
          flex: 0 0 auto;
          border-radius: 999px;
          background: rgba(255, 255, 255, 0.68);
          padding: 4px 8px;
          color: #9b5fa1;
          font-size: 11px;
          font-weight: 700;
          line-height: 1;
        }
        .games-card p {
          margin: 7px 0 0;
          overflow: hidden;
          color: #7b6a80;
          font-size: 13px;
          font-weight: 600;
          line-height: 1.35;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .games-board-strip {
          display: grid;
          grid-template-columns: repeat(7, minmax(0, 1fr));
          gap: 5px;
          margin-top: 10px;
          max-width: 230px;
        }
        .games-board-strip i {
          display: block;
          aspect-ratio: 1;
          border: 1px solid rgba(186, 104, 200, 0.18);
          border-radius: 7px;
          background: rgba(255, 255, 255, 0.62);
        }
        .games-board-strip .filled {
          background: #fff9c4;
        }
        .games-board-strip .me {
          background: #f8bbd0;
          box-shadow: inset 0 0 0 3px #ffffff;
        }
        .games-board-strip .du {
          background: #e1f5fe;
          box-shadow: inset 0 0 0 3px #ffffff;
        }
        .games-board-strip .finish {
          background: #e0f2f1;
        }
        `}
      </style>
    </div>
  );
}
