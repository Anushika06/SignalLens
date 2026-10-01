"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Globe2, Search, SearchX, X } from "lucide-react";

import { PageHeader, Section } from "@/components/common/page-header";
import { CardGridSkeleton } from "@/components/common/skeletons";
import { EmptyState, ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { plural } from "@/lib/format";
import { useEntities } from "@/lib/hooks";
import { routes } from "@/lib/routes";
import type { EntityRole } from "@/lib/types";

import { EntityCard } from "./entity-card";
import { matchesEntity, ROLE_GROUPS } from "./entity-roles";

type RoleFilter = EntityRole | "all";

/**
 * World state: every entity SignalLens keeps a versioned model of, grouped by the role it
 * plays for you (subjects first, context last).
 */
export function WorldScreen({ wid }: { wid: string }) {
  const { data: entities, error, isLoading, mutate } = useEntities(wid);
  const [query, setQuery] = useState("");
  const [role, setRole] = useState<RoleFilter>("all");

  const presentRoles = useMemo(
    () => ROLE_GROUPS.filter((group) => entities?.some((entity) => entity.role === group.role)),
    [entities],
  );

  const groups = useMemo(() => {
    const visible = (entities ?? []).filter(
      (entity) => (role === "all" || entity.role === role) && matchesEntity(entity, query),
    );
    return ROLE_GROUPS.map((group) => ({
      ...group,
      entities: visible
        .filter((entity) => entity.role === group.role)
        .sort((a, b) => a.name.localeCompare(b.name)),
    })).filter((group) => group.entities.length > 0);
  }, [entities, role, query]);

  const visibleCount = groups.reduce((sum, group) => sum + group.entities.length, 0);
  const filtering = query.trim() !== "" || role !== "all";

  return (
    <div className="space-y-8">
      <PageHeader
        title="World state"
        description="A versioned, evidence-backed model of the companies, products and regulators you monitor — not a chatbot. Every fact keeps its history and the sources behind it."
      />

      {isLoading ? (
        <CardGridSkeleton count={6} />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void mutate()} />
      ) : !entities || entities.length === 0 ? (
        <EmptyState
          icon={Globe2}
          title="No entities yet"
          description="The world state is built once your monitoring plan is approved and the first baseline completes. The companies, products and regulators in your plan — with their tracked facts and history — will appear here."
          action={
            <Button asChild variant="outline" size="sm">
              <Link href={routes.dashboard(wid)}>Go to the dashboard</Link>
            </Button>
          }
        />
      ) : (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <InputGroup className="sm:max-w-xs">
              <InputGroupInput
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search entities, aliases, domains"
                aria-label="Search entities"
              />
              <InputGroupAddon>
                <Search aria-hidden="true" />
              </InputGroupAddon>
              {query ? (
                <InputGroupAddon align="inline-end">
                  <InputGroupButton size="icon-xs" onClick={() => setQuery("")} aria-label="Clear search">
                    <X aria-hidden="true" />
                  </InputGroupButton>
                </InputGroupAddon>
              ) : null}
            </InputGroup>
            <Select value={role} onValueChange={(value) => setRole(value as RoleFilter)}>
              <SelectTrigger className="w-full sm:w-44" aria-label="Filter by role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All roles</SelectItem>
                {presentRoles.map((group) => (
                  <SelectItem key={group.role} value={group.role}>
                    {group.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="metric text-sm text-muted-foreground sm:ml-auto" aria-live="polite">
              {filtering
                ? `${visibleCount} of ${plural(entities.length, "entity", "entities")}`
                : plural(entities.length, "entity", "entities")}
            </p>
          </div>

          {groups.length === 0 ? (
            <EmptyState
              icon={SearchX}
              title="No entities match"
              description="Try another name, alias or domain, or clear the filters."
              action={
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setQuery("");
                    setRole("all");
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            groups.map((group) => (
              <Section
                key={group.role}
                id={`role-${group.role}`}
                title={
                  <>
                    {group.title} <span className="metric font-normal text-muted-foreground">{group.entities.length}</span>
                  </>
                }
                description={group.description}
              >
                <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  {group.entities.map((entity) => (
                    <li key={entity.id}>
                      <EntityCard wid={wid} entity={entity} />
                    </li>
                  ))}
                </ul>
              </Section>
            ))
          )}
        </>
      )}
    </div>
  );
}
