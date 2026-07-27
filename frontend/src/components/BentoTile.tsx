import type { ReactNode } from "react";

type Props = {
  title?: string;
  headerRight?: ReactNode;
  children: ReactNode;
  className?: string;
  span?: "chat" | "debug" | "queue" | "pipeline" | "stat" | "full";
  noPad?: boolean;
};

export default function BentoTile({
  title,
  headerRight,
  children,
  className = "",
  span,
  noPad = false,
}: Props) {
  const spanClass = span ? `bento-tile--${span}` : "";
  return (
    <section className={`bento-tile ${spanClass} ${className}`.trim()}>
      {(title || headerRight) && (
        <header className="bento-tile__header">
          {title ? <h2 className="bento-tile__title">{title}</h2> : <span />}
          {headerRight}
        </header>
      )}
      <div className={noPad ? "bento-tile__body bento-tile__body--flush" : "bento-tile__body"}>
        {children}
      </div>
    </section>
  );
}
