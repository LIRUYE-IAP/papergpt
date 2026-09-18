import Link from "next/link";

export default function Home() {
  return (
    <main className="landing-shell">
      <nav className="landing-nav">
        <span className="brand">PaperGPT</span>
        <div className="header-actions">
          <Link href="/login" className="text-link">登录</Link>
          <Link href="/register" className="primary-button">创建账户</Link>
        </div>
      </nav>
      <section className="hero">
        <p className="eyebrow">Your personal paper workspace</p>
        <h1>把论文收藏在一个安静、清晰的地方。</h1>
        <p>安全上传 PDF、建立个人论文库，并为后续的阅读与研究工作流做好准备。</p>
        <div className="hero-actions">
          <Link href="/register" className="primary-button">开始使用</Link>
          <Link href="/login" className="secondary-button">已有账户</Link>
        </div>
      </section>
    </main>
  );
}
