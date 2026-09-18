"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { apiRequest, setToken, User } from "@/lib/api";

type AuthFormProps = {
  mode: "login" | "register";
};

export default function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const isRegister = mode === "register";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (isRegister) {
        await apiRequest<User>("/auth/register", {
          method: "POST",
          body: JSON.stringify({ name, email, password }),
        });
        router.push("/login");
      } else {
        const result = await apiRequest<{ access_token: string }>("/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        setToken(result.access_token);
        router.push("/library");
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "请求失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <Link href="/" className="brand">PaperGPT</Link>
        <div>
          <p className="eyebrow">{isRegister ? "创建账户" : "欢迎回来"}</p>
          <h1>{isRegister ? "开始管理你的论文" : "登录 PaperGPT"}</h1>
          <p className="muted">Phase 1 提供安全账户、PDF 上传与个人论文库。</p>
        </div>
        <form onSubmit={handleSubmit} className="form-stack">
          {isRegister && (
            <label>
              姓名
              <input value={name} onChange={(event) => setName(event.target.value)} required maxLength={255} />
            </label>
          )}
          <label>
            邮箱
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="email" />
          </label>
          <label>
            密码
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={isRegister ? 8 : 1} maxLength={128} autoComplete={isRegister ? "new-password" : "current-password"} />
          </label>
          {error && <p className="error-message" role="alert">{error}</p>}
          <button className="primary-button" disabled={submitting}>
            {submitting ? "请稍候…" : isRegister ? "注册" : "登录"}
          </button>
        </form>
        <p className="auth-switch">
          {isRegister ? "已有账户？" : "还没有账户？"}{" "}
          <Link href={isRegister ? "/login" : "/register"}>{isRegister ? "去登录" : "去注册"}</Link>
        </p>
      </section>
    </main>
  );
}
