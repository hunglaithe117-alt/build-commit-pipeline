import Link from "next/link";

const sections = [
  {
    title: "Quản lý project",
    description: "Tải CSV TravisTorrent, cấu hình sonar.properties và khởi chạy pipeline.",
    href: "/projects",
  },
  {
    title: "Scan jobs",
    description: "Giám sát trạng thái commit, số lần retry và worker đang chạy.",
    href: "/jobs",
  },
  {
    title: "Kết quả quét",
    description: "Xem metrics thu thập được từ SonarQube cho từng commit.",
    href: "/sonar-runs",
  },
  {
    title: "Failed commits",
    description: "Xem và retry các commit FAILED_PERMANENT với cấu hình tuỳ chỉnh.",
    href: "/failed-commits",
  },
];

export default function Home() {
  return (
    <section className="grid gap-6 md:grid-cols-2">
      {sections.map((section) => (
        <Link
          key={section.href}
          className="rounded-xl border bg-card p-6 text-card-foreground shadow-sm transition hover:border-slate-300 hover:shadow-md"
          href={section.href}
        >
          <h2 className="text-xl font-semibold">{section.title}</h2>
          <p className="mt-2 text-sm text-muted-foreground">{section.description}</p>
        </Link>
      ))}
    </section>
  );
}
