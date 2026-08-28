import React from "react";
import { Link, useLocation } from "react-router-dom";

const EFFECTIVE_DATE = "August 28, 2026";

export default function Legal() {
  const { pathname } = useLocation();
  const privacy = pathname === "/privacy";
  return (
    <main className="min-h-screen bg-background text-foreground px-5 py-10">
      <article className="max-w-3xl mx-auto bg-card border border-border p-6 md:p-10">
        <p className="font-mono text-xs tracking-[0.25em] uppercase text-primary mb-3">Squawk King IA</p>
        <h1 className="font-head font-black text-3xl uppercase mb-2">
          {privacy ? "Privacy Policy" : "Terms & Aviation Safety"}
        </h1>
        <p className="text-xs text-muted-foreground mb-8">Effective {EFFECTIVE_DATE}</p>

        {privacy ? (
          <div className="space-y-6 text-sm leading-7">
            <section><h2 className="font-bold text-lg mb-1">Information collected</h2><p>We collect account information, aircraft profiles, troubleshooting sessions, logbook drafts, uploaded manuals and media, payment status, and technical logs required to operate and secure the service.</p></section>
            <section><h2 className="font-bold text-lg mb-1">How information is used</h2><p>Information is used to provide troubleshooting tools, retrieve user-supplied maintenance references, manage subscriptions, prevent abuse, improve reliability, and respond to support or safety reports.</p></section>
            <section><h2 className="font-bold text-lg mb-1">Service providers</h2><p>Necessary data may be processed by hosting, database, file-storage, AI, email, and payment providers. Payment-card details are processed by the payment provider and are not stored by Squawk King IA.</p></section>
            <section><h2 className="font-bold text-lg mb-1">Retention and deletion</h2><p>Data is retained while the account is active and as legally required. An account and its associated user content can be permanently deleted from Account Settings. Payment and transaction records may be retained when required for tax, fraud-prevention, or legal compliance.</p></section>
            <section><h2 className="font-bold text-lg mb-1">Security and contact</h2><p>Reasonable safeguards are used, but no online system is risk-free. Privacy or deletion questions may be sent to the support address shown in the app-store listing or website.</p></section>
          </div>
        ) : (
          <div className="space-y-6 text-sm leading-7">
            <section className="border-l-4 border-accent pl-4"><h2 className="font-bold text-lg mb-1">Not approved maintenance data</h2><p>Squawk King IA is a troubleshooting support tool. It does not replace current applicable manufacturer maintenance data, FAA-approved data, ADs, ICA, the aircraft records, or the independent judgment and responsibility of an appropriately certificated person.</p></section>
            <section><h2 className="font-bold text-lg mb-1">User responsibility</h2><p>Users must verify aircraft identity, configuration, applicability, revision status, limits, procedures, and return-to-service requirements before performing or approving maintenance. Do not rely on an AI response when approved data is missing, unclear, or conflicts with the response.</p></section>
            <section><h2 className="font-bold text-lg mb-1">AI limitations</h2><p>AI output can be incomplete, outdated, or wrong. Stop work and consult controlling approved data whenever an answer cannot be independently verified. Potentially unsafe or incorrect output should be reported using the in-app flag control.</p></section>
            <section><h2 className="font-bold text-lg mb-1">Subscriptions</h2><p>Paid access renews according to the price and period shown at checkout until canceled. Trial, cancellation, refund, and renewal terms displayed by the payment provider are part of the purchase terms.</p></section>
            <section><h2 className="font-bold text-lg mb-1">Uploaded material</h2><p>Users may upload only material they are authorized to possess and process. Users retain responsibility for copyright, confidentiality, export, and employer restrictions.</p></section>
          </div>
        )}

        <div className="mt-10 pt-5 border-t border-border flex flex-wrap gap-4 font-mono text-xs">
          <Link to={privacy ? "/terms" : "/privacy"} className="text-primary hover:underline">
            {privacy ? "Terms & Safety" : "Privacy Policy"}
          </Link>
          <Link to="/" className="text-muted-foreground hover:text-foreground">Return to app</Link>
        </div>
      </article>
    </main>
  );
}
