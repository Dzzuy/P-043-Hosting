import { useState } from 'react';

const DEMO_ACCOUNTS = [
  { role: 'advisor', label: 'Tư vấn viên', username: 'advisor.demo', password: 'DemoAdvisor123!' },
  { role: 'manager', label: 'Quản lý', username: 'manager.demo', password: 'DemoManager123!' },
];

function Icon({ name, size = 18, strokeWidth = 1.8 }) {
  const paths = {
    mail: (
      <>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="M3 7l9 6 9-6" />
      </>
    ),
    lock: (
      <>
        <rect x="4" y="11" width="16" height="10" rx="2" />
        <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      </>
    ),
    arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
    chevron: <path d="M9 6l6 6-6 6" />,
    advisor: (
      <>
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21c0-4 3.6-7 8-7s8 3 8 7" />
      </>
    ),
    manager: (
      <>
        <circle cx="9" cy="8" r="3.5" />
        <path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6" />
        <path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5c2.2.6 3.5 2.4 3.5 5.5" />
      </>
    ),
    lookup: (
      <>
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4" />
        <path d="M14 3l5 5v3" />
        <path d="M14 3v5h5" />
        <circle cx="16" cy="17" r="3" />
        <path d="M21 22l-3-3" />
      </>
    ),
    practice: (
      <>
        <path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        <path d="M8 8h8M8 12h5" />
      </>
    ),
    evaluate: (
      <>
        <rect x="4" y="11" width="4" height="9" rx="1" />
        <rect x="10" y="4" width="4" height="16" rx="1" />
        <rect x="16" y="8" width="4" height="12" rx="1" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

export function LoginView({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const selectDemoAccount = (demoUsername, demoPassword) => {
    setUsername(demoUsername);
    setPassword(demoPassword);
    setShowPassword(false);
    setError('');
  };

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    if (!username.trim() || !password) {
      setError('Vui lòng nhập tên đăng nhập và mật khẩu.');
      return;
    }
    setIsLoading(true);
    try {
      await onLogin(username.trim(), password);
    } catch (loginError) {
      setError(loginError.message || 'Đăng nhập thất bại. Vui lòng thử lại.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="login-showcase" aria-label="Giới thiệu AI Sales Coach">
        <img className="login-showcase-car" src="/login-car-showroom.jpg" alt="" />

        <div className="login-brand">
          <span className="login-logo"><img src="/vinfast-official-logo.png?v=silver" alt="VinFast" /></span>
          <div>
            <div className="login-brand-title">AI Sales Coach &amp; Co-pilot</div>
            <p>Nền tảng đào tạo và hỗ trợ tư vấn bán hàng ô tô</p>
          </div>
        </div>

        <h1 className="login-headline">Luyện tập tốt hơn.<br />Tư vấn tự tin hơn.</h1>

        <div className="login-pitch">
          <p>Mô phỏng hội thoại khách hàng, tra cứu thông tin có nguồn và đánh giá kỹ năng trong một hệ thống thống nhất.</p>
          <div className="login-features">
            <article>
              <span className="login-feature-icon"><Icon name="lookup" size={28} strokeWidth={1.5} /></span>
              <strong>Tra cứu<br />có nguồn</strong>
            </article>
            <article>
              <span className="login-feature-icon"><Icon name="practice" size={28} strokeWidth={1.5} /></span>
              <strong>Luyện tập<br />theo tình huống</strong>
            </article>
            <article>
              <span className="login-feature-icon"><Icon name="evaluate" size={28} strokeWidth={1.5} /></span>
              <strong>Đánh giá<br />kỹ năng</strong>
            </article>
          </div>
        </div>
      </section>

      <section className="login-panel">
        <div className="login-form-wrap">
          <div className="login-mobile-brand">
            <span className="login-logo"><img src="/vinfast-official-logo.png?v=silver" alt="VinFast" /></span>
            <strong>AI Sales Coach &amp; Co-pilot</strong>
          </div>
          <header>
            <h2>Chào mừng bạn trở lại</h2>
            <p>Đăng nhập để tiếp tục sử dụng hệ thống.</p>
          </header>

          {error && <div className="login-error" role="alert">{error}</div>}

          <form onSubmit={submit} className="login-form">
            <label>
              <span>Email hoặc tên đăng nhập</span>
              <span className="login-input-wrap">
                <span className="login-field-icon"><Icon name="mail" /></span>
                <input
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="advisor.demo"
                  disabled={isLoading}
                />
              </span>
            </label>

            <label>
              <span>Mật khẩu</span>
              <span className="login-input-wrap">
                <span className="login-field-icon"><Icon name="lock" /></span>
                <input
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Nhập mật khẩu"
                  disabled={isLoading}
                />
                <button
                  className="login-password-toggle"
                  type="button"
                  onClick={() => setShowPassword((visible) => !visible)}
                  aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                >
                  {showPassword ? 'Ẩn' : 'Hiện'}
                </button>
              </span>
            </label>

            <button className="login-submit" type="submit" disabled={isLoading}>
              {isLoading ? 'Đang đăng nhập…' : <>Đăng nhập <Icon name="arrow" strokeWidth={2} /></>}
            </button>
          </form>

          <div className="login-divider" aria-hidden="true"><span>Hoặc</span></div>

          <div className="login-demo">
            <h3>Dùng thử nhanh</h3>
            <p>Chọn tài khoản mẫu theo vai trò.</p>
            <div className="login-demo-cards">
              {DEMO_ACCOUNTS.map((account) => {
                const selected = username === account.username && password === account.password;
                return (
                  <button
                    key={account.role}
                    type="button"
                    className={`login-demo-card ${account.role}${selected ? ' selected' : ''}`}
                    aria-pressed={selected}
                    onClick={() => selectDemoAccount(account.username, account.password)}
                    disabled={isLoading}
                  >
                    <span className="login-demo-card-heading">
                      <strong><Icon name={account.role} />{account.label}</strong>
                      <Icon name="chevron" size={16} strokeWidth={2} />
                    </span>
                    <span className="login-demo-card-details">
                      <span>Tài khoản:</span><span>{account.username}</span>
                      <span>Mật khẩu:</span><span>{account.password}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
