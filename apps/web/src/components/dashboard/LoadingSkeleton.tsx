export function LoadingSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div aria-label="Loading" role="status" className="skeleton-list">
      {Array.from({ length: rows }, (_, index) => (
        <i key={index} />
      ))}
    </div>
  );
}
