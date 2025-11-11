const sections = [
  {
    title: "Quản lý nguồn dữ liệu",
    description: "Tải file CSV TravisTorrent, xem thống kê tổng quan và khởi chạy pipeline.",
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
];

export default function Home() {
  return (
    <section className="grid">
      {sections.map((section) => (
        <a key={section.href} className="card" href={section.href}>
          <h2>{section.title}</h2>
          <p>{section.description}</p>
        </a>
      ))}
    </section>
  );
}
