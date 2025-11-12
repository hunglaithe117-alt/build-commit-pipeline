import Link from "next/link";

const sections = [
  {
    title: "Quản lý nguồn dữ liệu",
    description: "Tải file CSV TravisTorrent, cấu hình sonar.properties và khởi chạy pipeline.",
    href: "/data-sources",
  },
  {
    title: "Job thu thập",
    description: "Giám sát tiến độ các data job, số commit đã xử lý và trạng thái retry.",
    href: "/jobs",
  },
  {
    title: "SonarQube",
    description: "Quan sát lịch sử quét, trạng thái webhook và lần export gần nhất.",
    href: "/sonar-runs",
  },
  {
    title: "Dữ liệu đầu ra",
    description: "Xem metrics đã thu thập và tải nhanh các tập dữ liệu enriched.",
    href: "/outputs",
  },
  {
    title: "Deadletter commits",
    description: "Theo dõi commit lỗi, tinh chỉnh cấu hình sonar và retry từng commit.",
    href: "/dead-letters",
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
