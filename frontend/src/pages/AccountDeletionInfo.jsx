import React from "react";
import { Link } from "react-router-dom";

export default function AccountDeletionInfo() {
  return (
    <main className="min-h-screen bg-background text-foreground px-6 py-12">
      <article className="max-w-2xl mx-auto space-y-6">
        <h1 className="font-head font-black text-4xl uppercase">Delete Your Account</h1>
        <p>To permanently delete a Squawk King IA account and its associated data:</p>
        <ol className="list-decimal pl-6 space-y-2">
          <li>Sign in through this website.</li>
          <li>Open Account Settings from the user section.</li>
          <li>Enter your password, type DELETE, and confirm.</li>
        </ol>
        <p>This deletes aircraft profiles, troubleshooting sessions and messages, logbook drafts, uploaded manuals and media, and account records. Any active Stripe customer is canceled first. Payment providers may retain limited transaction records when legally required.</p>
        <p>If you cannot sign in, email joepalmas82@gmail.com from the account email address and request deletion.</p>
        <div className="flex gap-4">
          <Link className="text-primary underline" to="/login">Sign in</Link>
          <Link className="text-primary underline" to="/privacy">Privacy policy</Link>
        </div>
      </article>
    </main>
  );
}
