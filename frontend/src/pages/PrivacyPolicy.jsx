import React from "react";
import { Link } from "react-router-dom";

export default function PrivacyPolicy() {
  return (
    <main className="min-h-screen bg-background text-foreground px-6 py-12">
      <article className="max-w-3xl mx-auto space-y-6">
        <h1 className="font-head font-black text-4xl uppercase">Privacy Policy</h1>
        <p className="text-muted-foreground">Effective August 28, 2026</p>
        <p>JP3 Aviation provides Squawk King IA, an aircraft-maintenance troubleshooting service.</p>
        <section>
          <h2 className="font-head font-bold text-xl mb-2">Information collected</h2>
          <p>We collect account information, aircraft profiles, troubleshooting conversations, logbook drafts, uploaded manuals and media, subscription status, and technical logs needed to operate and secure the service.</p>
        </section>
        <section>
          <h2 className="font-head font-bold text-xl mb-2">How information is used</h2>
          <p>Information is used to authenticate users, provide troubleshooting results, store user records, process subscriptions, deliver account email, prevent abuse, and improve reliability.</p>
        </section>
        <section>
          <h2 className="font-head font-bold text-xl mb-2">Service providers</h2>
          <p>Data may be processed by hosting and storage providers, OpenAI or the configured AI provider, Stripe for billing, and Resend for transactional email. We do not sell personal information.</p>
        </section>
        <section>
          <h2 className="font-head font-bold text-xl mb-2">Retention and deletion</h2>
          <p>Account data is retained while the account is active. Users may permanently delete their account and associated service data from Account Settings. Limited transaction records may be retained by payment providers where legally required.</p>
          <Link className="text-primary underline" to="/account-deletion">Account-deletion instructions</Link>
        </section>
        <section>
          <h2 className="font-head font-bold text-xl mb-2">Security and contact</h2>
          <p>Traffic is encrypted in transit and access is authenticated. No system is guaranteed completely secure. Privacy questions may be sent to joepalmas82@gmail.com.</p>
        </section>
        <p className="text-sm text-muted-foreground">Squawk King IA is a troubleshooting aid and does not replace approved maintenance data or the judgment and responsibility of a certificated person.</p>
        <Link className="text-primary underline" to="/">Return to Squawk King IA</Link>
      </article>
    </main>
  );
}
