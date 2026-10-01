import { Skeleton } from "@/components/ui/skeleton";

/** Placeholder with the same shape as an intelligence card, so the page doesn't jump on load. */
export function ReportSkeleton() {
  return (
    <div className="space-y-8" aria-busy="true" aria-label="Loading intelligence card">
      <div className="space-y-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-64 max-w-full" />
        <Skeleton className="h-8 w-full max-w-2xl" />
        <div className="flex gap-2">
          <Skeleton className="h-5 w-16" />
          <Skeleton className="h-5 w-24" />
        </div>
        <Skeleton className="h-3 w-48" />
      </div>
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          <Skeleton className="h-28 w-full rounded-xl" />
          <Skeleton className="h-56 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
        </div>
        <div className="space-y-4">
          <Skeleton className="h-44 w-full rounded-xl" />
          <Skeleton className="h-72 w-full rounded-xl" />
        </div>
      </div>
    </div>
  );
}
