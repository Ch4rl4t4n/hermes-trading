import { useEffect, useState } from "react";

export function useBreakpoint() {
  const initial = typeof window === "undefined" ? 1440 : window.innerWidth;
  const [width, setWidth] = useState(initial);

  useEffect(() => {
    const handler = () => setWidth(window.innerWidth);
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, []);

  return {
    isMobile: width < 768,
    isTablet: width >= 768 && width < 1024,
    isDesktop: width >= 1024,
    width,
  };
}

