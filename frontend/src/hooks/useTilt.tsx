import { useRef, useState, type CSSProperties, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  className?: string;
  maxTilt?: number;
};

export function useTilt(maxTilt = 6) {
  const ref = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<CSSProperties>({});

  const coarse =
    typeof window !== "undefined" &&
    window.matchMedia("(pointer: coarse)").matches;

  function onMove(e: React.MouseEvent<HTMLDivElement>) {
    if (coarse || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top) / rect.height - 0.5;
    setStyle({
      transform: `perspective(800px) rotateX(${-y * maxTilt}deg) rotateY(${x * maxTilt}deg)`,
    });
  }

  function onLeave() {
    setStyle({ transform: "perspective(800px) rotateX(0deg) rotateY(0deg)" });
  }

  return { ref, style, onMove, onLeave, coarse };
}

export default function TiltWrap({ children, className = "", maxTilt = 6 }: Props) {
  const { ref, style, onMove, onLeave, coarse } = useTilt(maxTilt);

  return (
    <div
      ref={ref}
      className={`tilt-wrap ${className}`}
      style={coarse ? undefined : style}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
    >
      {children}
    </div>
  );
}
