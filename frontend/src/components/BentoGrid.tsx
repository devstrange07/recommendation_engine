import type { ReactNode } from "react";

type Layout = "chat" | "review" | "custom";

type Props = {
  layout?: Layout;
  className?: string;
  children: ReactNode;
  style?: React.CSSProperties;
};

export default function BentoGrid({ layout = "custom", className = "", children, style }: Props) {
  const layoutClass =
    layout === "chat" ? "bento-grid--chat" : layout === "review" ? "bento-grid--review" : "";
  return (
    <div className={`bento-grid ${layoutClass} ${className}`.trim()} style={style}>
      {children}
    </div>
  );
}
