"use client";

import { TagInput } from "@/components/common/tag-input";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { CompanyProfile } from "@/lib/types";

export const EMPTY_PROFILE: CompanyProfile = {
  company_name: "",
  website: null,
  description: "",
  products: [],
  markets: [],
  competitors: [],
  relationship_to_subjects: "",
};

/** True when the user has filled in at least one profile field. */
export function hasProfileContent(profile: CompanyProfile) {
  return Boolean(
    profile.company_name.trim() ||
      profile.website?.trim() ||
      profile.description.trim() ||
      profile.products.length ||
      profile.markets.length ||
      profile.competitors.length ||
      profile.relationship_to_subjects.trim(),
  );
}

type CompanyProfileFieldsProps = {
  value: CompanyProfile;
  onChange: (next: CompanyProfile) => void;
  /** Prefix for input ids when the form appears more than once on a page. */
  idPrefix?: string;
  disabled?: boolean;
};

/**
 * "Us": who the customer is. Impact analysis uses it to explain why a change matters to this
 * company, and routing uses it to decide who hears about it. Shared by onboarding and Settings.
 */
export function CompanyProfileFields({ value, onChange, idPrefix = "profile", disabled }: CompanyProfileFieldsProps) {
  const id = (name: string) => `${idPrefix}-${name}`;
  const set = <K extends keyof CompanyProfile>(key: K, next: CompanyProfile[K]) => onChange({ ...value, [key]: next });

  return (
    <FieldGroup className="gap-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <Field>
          <FieldLabel htmlFor={id("company")}>Company name</FieldLabel>
          <Input
            id={id("company")}
            value={value.company_name}
            onChange={(event) => set("company_name", event.target.value)}
            placeholder="Kivo Payments"
            autoComplete="organization"
            disabled={disabled}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor={id("website")}>Website</FieldLabel>
          <Input
            id={id("website")}
            type="url"
            inputMode="url"
            value={value.website ?? ""}
            onChange={(event) => set("website", event.target.value.trim() ? event.target.value : null)}
            placeholder="https://kivo.example"
            disabled={disabled}
          />
        </Field>
      </div>
      <Field>
        <FieldLabel htmlFor={id("description")}>What you do, and for whom</FieldLabel>
        <Textarea
          id={id("description")}
          value={value.description}
          onChange={(event) => set("description", event.target.value)}
          placeholder="Payment gateway for Indian SMBs and D2C brands: checkout, payouts and payment links."
          rows={3}
          disabled={disabled}
        />
      </Field>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field>
          <FieldLabel htmlFor={id("products")}>Products</FieldLabel>
          <TagInput
            id={id("products")}
            value={value.products}
            onChange={(next) => set("products", next)}
            placeholder="Type and press Enter"
            disabled={disabled}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor={id("markets")}>Markets and segments</FieldLabel>
          <TagInput
            id={id("markets")}
            value={value.markets}
            onChange={(next) => set("markets", next)}
            placeholder="India, SMB merchants…"
            disabled={disabled}
          />
        </Field>
      </div>
      <Field>
        <FieldLabel htmlFor={id("competitors")}>Competitors you already know</FieldLabel>
        <TagInput
          id={id("competitors")}
          value={value.competitors}
          onChange={(next) => set("competitors", next)}
          placeholder="Razorpay, Cashfree…"
          disabled={disabled}
          aria-describedby={id("competitors-hint")}
        />
        <FieldDescription id={id("competitors-hint")}>
          The planner uses these as a starting point and may suggest others.
        </FieldDescription>
      </Field>
      <Field>
        <FieldLabel htmlFor={id("relationship")}>Your relationship to what you monitor</FieldLabel>
        <Textarea
          id={id("relationship")}
          value={value.relationship_to_subjects}
          onChange={(event) => set("relationship_to_subjects", event.target.value)}
          placeholder="Razorpay is our most direct competitor in SMB onboarding."
          rows={2}
          disabled={disabled}
          aria-describedby={id("relationship-hint")}
        />
        <FieldDescription id={id("relationship-hint")}>
          Competitor, customer, partner or investor? The same change means different things to each.
        </FieldDescription>
      </Field>
    </FieldGroup>
  );
}
