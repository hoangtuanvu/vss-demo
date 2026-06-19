import Link from "next/link";

export default function Home() {
  return (
    <main>
      <h1>Warehouse Safety Monitor</h1>
      <nav>
        <Link href="/upload">Upload</Link>
        <Link href="/monitor">Live Monitor</Link>
        <Link href="/stats">Stats</Link>
      </nav>
    </main>
  );
}
