import Link from "next/link";
import { Shell } from "@/components/layout/Shell";

export default function Home() {
  return (
    <Shell>
      <div className="space-y-6">
        <header className="space-y-3">
          <h1 className="font-serif text-4xl tracking-tight text-ink leading-snug">
            RAG Benchmark
          </h1>
          <p className="font-serif text-2xl text-slate leading-[1.7] max-w-prose">
            Create datasets, configure a RAG pipeline, and run the processing step against your
            document collection.
          </p>
        </header>

        <div className="flex flex-col sm:flex-row gap-3">
          <Link
            href="/datasets"
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-coral text-white font-sans font-medium text-sm rounded-md border border-transparent hover:bg-coral-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-coral focus-visible:ring-offset-2 transition-colors duration-150 ease-out"
          >
            Open datasets
          </Link>
          <Link
            href="/run"
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-transparent text-charcoal font-sans font-medium text-sm rounded-md border border-linen hover:bg-linen hover:border-dune focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-coral focus-visible:ring-offset-2 transition-colors duration-150 ease-out"
          >
            Configure & run
          </Link>
        </div>
      </div>
    </Shell>
  );
}

