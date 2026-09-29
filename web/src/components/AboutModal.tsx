"use client";

import { useEffect } from "react";
import { X } from "lucide-react";
import type { MetaOptions } from "@/lib/api";

/** 모델 설명 — 지표 정의, 계산 흐름, 데이터 출처와 한계. */
export default function AboutModal({
  open,
  onClose,
  meta,
}: {
  open: boolean;
  onClose: () => void;
  meta: MetaOptions | null;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center">
      <button className="absolute inset-0 bg-ink/40" onClick={onClose} aria-label="닫기" />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-title"
        className="relative bg-surface w-full md:max-w-2xl max-h-[88vh] overflow-y-auto rounded-t-lg md:rounded-lg border border-line shadow-xl"
      >
        <div className="sticky top-0 bg-surface border-b border-line flex items-center justify-between px-5 h-12">
          <h2 id="about-title" className="text-[15px] font-semibold">모델 설명</h2>
          <button onClick={onClose} className="p-1.5 text-muted hover:text-ink" aria-label="닫기">
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-5 space-y-6 text-[13.5px] leading-relaxed text-ink-2">
          <section className="space-y-2">
            <p>
              서울 핵심 17개 구에 매물로 나온 빌딩·상가를 모아, 지금 호가로 사서 허용 용적률만큼
              새로 지었을 때 <b className="text-ink">호텔과 오피스 중 무엇이 사업성이 나오는지</b>를
              추정합니다. 붙어 있는 필지는 묶어서 합필 개발도 함께 계산합니다.
            </p>
          </section>

          <section>
            <h3 className="text-xs font-semibold text-muted tracking-wide mb-2">계산 흐름</h3>
            <ol className="space-y-2 list-decimal pl-5 marker:text-faint marker:font-mono">
              <li>
                개발 연면적 = 대지 × 용도지역 최대 용적률(지상) + 대지 × 60%(지하). 한양도성 안
                상업지역은 역사도심 조례 용적률(일반상업 600%, 근린·유통 500%)
              </li>
              <li>
                총사업비 = 매입가 + 공사비(연면적 × 평당 공사비) + 부대비 6% + 건설이자(LTV 60%, 2년)
              </li>
              <li>
                <b className="text-ink">호텔</b>: 연면적으로 3·4·5성급을 나누고 ADR × 점유율 × 객실수로
                매출 → GOP → NOI (운영사 수수료, FF&amp;E 적립, 재산세 차감)
              </li>
              <li>
                <b className="text-ink">오피스</b>: 전용면적(연면적 × 50%) × 권역별 NOC × 12 − 임대면적 ×
                운용비 3만원/평/월 × 12 = NOI
              </li>
              <li>
                <b className="text-ink">취득 Cap</b> = 안정화 NOI ÷ 총사업비.
                &lsquo;최적 용도&rsquo;는 상업·준주거·준공업 지역에서 둘 중 높은 쪽을 고릅니다.
              </li>
              <li>
                매물을 누르면 공사 기간·안정화·매각까지의 현금흐름으로 IRR, NPV, 회수기간을 계산합니다.
              </li>
            </ol>
          </section>

          <section>
            <h3 className="text-xs font-semibold text-muted tracking-wide mb-2">권역 구분 (오피스)</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-line border border-line rounded overflow-hidden text-[12.5px]">
              {[
                ["CBD", "중구 · 종로구"],
                ["GBD", "강남구 · 서초구"],
                ["YBD", "영등포구 · 마포구"],
                ["기타", "그 외 자치구"],
              ].map(([k, v]) => (
                <div key={k} className="bg-surface px-3 py-2">
                  <div className="font-mono text-[11px] text-muted">{k}</div>
                  <div>{v}</div>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-xs font-semibold text-muted tracking-wide mb-2">데이터와 한계</h3>
            <ul className="space-y-1.5 list-disc pl-5 marker:text-faint">
              <li>
                매물: 네이버부동산에 공개된 매매 호가
                {meta?.data_as_of && <> (기준일 <span className="num">{meta.data_as_of}</span>)</>}. 실거래가가 아닙니다.
              </li>
              <li>용도지역·건축물 정보: 건축물대장, 필지 경계: 국토부 VWorld.</li>
              <li>지하철 노선·역: © OpenStreetMap contributors (ODbL), 자치구 경계: 통계청.</li>
              <li>
                ADR, NOC, 공사비, 매각 Cap 같은 가정값은 공개 리포트 수준의 대략치이며 좌측
                &lsquo;시뮬 가정값&rsquo;에서 바꿀 수 있습니다.
              </li>
              <li>
                인허가(지구단위계획, 높이 제한, 주차), 기존 임차인, 명도 비용은 반영하지 않습니다.
              </li>
              <li>중개사 연락처 등 개인정보는 수집·표시하지 않습니다.</li>
            </ul>
          </section>

          <p className="text-[12px] text-faint border-t border-line pt-4">
            개인 포트폴리오 프로젝트입니다. 네이버와 제휴하지 않았고, 투자 판단의 근거로 쓰도록
            만든 도구가 아닙니다.
          </p>
        </div>
      </div>
    </div>
  );
}
