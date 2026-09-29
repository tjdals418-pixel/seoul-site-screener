import type { NextConfig } from "next";

const API_TARGET = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // 개발 서버에 127.0.0.1로 접속해도 HMR 허용
  allowedDevOrigins: ["127.0.0.1", "localhost"],

  // mapbox-gl SSR 시 window 참조 에러 회피
  transpilePackages: ["mapbox-gl"],

  // 개발 모드 좌하단 표시 끔 (스크린샷·화면 녹화용)
  devIndicators: false,

  // 로컬 개발: /api/* 를 FastAPI(127.0.0.1:8000)로 전달.
  // Vercel 배포: 루트 vercel.json의 services 라우팅이 /api/* 를 api 서비스로 보내므로
  // 여기서는 프록시하지 않는다 (API_PROXY_TARGET을 주면 그 주소로 전달).
  async rewrites() {
    if (process.env.VERCEL && !process.env.API_PROXY_TARGET) return [];
    return [
      { source: "/api/:path*", destination: `${API_TARGET}/api/:path*` },
    ];
  },
};

export default nextConfig;
