// One graded story photo from public/story (AVIF with a WebP fallback, two widths). Decorative: the chapter text carries the meaning.
// Sources and licences: public/ASSETS.md.
export function Photo({ name, className, eager, active }: { name: string; className?: string; eager?: boolean; active?: boolean }) {
  const set = (ext: string) => `/story/${name}-960.${ext} 960w, /story/${name}-1600.${ext} 1600w`;
  return (
    <picture className={className} data-active={active}>
      <source type="image/avif" srcSet={set("avif")} sizes="100vw" />
      <source type="image/webp" srcSet={set("webp")} sizes="100vw" />
      <img src={`/story/${name}-1600.webp`} alt="" width={1600} height={1000} loading={eager ? "eager" : "lazy"} decoding="async" fetchPriority={eager ? "high" : "auto"} />
    </picture>
  );
}
