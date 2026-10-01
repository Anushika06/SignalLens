/**
 * A workspace name derived from the monitoring request, used when the user leaves the name
 * blank: "I want to monitor Razorpay" → "Razorpay", "Monitor Tata Motors' EV business" →
 * "Tata Motors", "Monitor Pfizer's pipeline and regulatory approvals" → "Pfizer".
 */
export function deriveWorkspaceName(request: string): string {
  const text = request.trim().replace(/\s+/g, " ").replace(/[.!?]+$/, "");
  if (!text) return "";

  const afterVerb = text.match(/\b(?:monitor|monitoring|track|tracking|watch|watching|follow|following)\s+(.+)/i);
  let subject = afterVerb?.[1] ?? text;

  // Stop at a possessive ("Stripe's pricing") or at the first connective or list separator.
  const possessive = subject.match(/^(.+?)(?:'s|’s|'|’)(?:\s|$)/);
  subject = possessive
    ? possessive[1]
    : (subject.split(/,|;|\s[-–—]\s|\s(?:and|for|in|on|with|including|across|especially)\s/i)[0] ?? subject);
  subject = subject.replace(/^(?:the|our|all|of)\s+/i, "").trim();
  if (!subject) return "";

  const words = subject.split(" ").slice(0, 5).join(" ");
  const name = words.charAt(0).toUpperCase() + words.slice(1);
  return name.length > 60 ? `${name.slice(0, 57).trimEnd()}…` : name;
}
