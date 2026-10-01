import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

export function ListSkeleton({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("divide-y rounded-xl border", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex items-center gap-3 px-4 py-3.5">
          <Skeleton className="size-2 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-3/5" />
            <Skeleton className="h-3 w-2/5" />
          </div>
          <Skeleton className="h-5 w-20" />
        </div>
      ))}
    </div>
  );
}

export function CardGridSkeleton({ count = 3, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("grid gap-4 sm:grid-cols-2 lg:grid-cols-3", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="space-y-3 rounded-xl border p-4">
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-3 w-4/5" />
          <Skeleton className="h-3 w-3/5" />
        </div>
      ))}
    </div>
  );
}

export function TableSkeleton({
  rows = 6,
  columns = 5,
  className,
}: {
  rows?: number;
  columns?: number;
  className?: string;
}) {
  return (
    <div className={cn("overflow-hidden rounded-xl border", className)} aria-busy="true" aria-label="Loading">
      <div className="flex gap-4 border-b bg-muted/40 px-4 py-2.5">
        {Array.from({ length: columns }, (_, index) => (
          <Skeleton key={index} className="h-3 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }, (_, row) => (
        <div key={row} className="flex gap-4 border-b px-4 py-3 last:border-0">
          {Array.from({ length: columns }, (_, col) => (
            <Skeleton key={col} className={cn("h-4 flex-1", col === 0 && "flex-[2]")} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function PageSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("space-y-8", className)} aria-busy="true" aria-label="Loading">
      <div className="space-y-2">
        <Skeleton className="h-7 w-72 max-w-full" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <CardGridSkeleton />
      <ListSkeleton rows={4} />
    </div>
  );
}
