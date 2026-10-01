import type { Metadata } from "next";

import { OnboardingWizard } from "@/components/onboarding/onboarding-wizard";

export const metadata: Metadata = { title: "New workspace" };

export default function Page() {
  return <OnboardingWizard />;
}
