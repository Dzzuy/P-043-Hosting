import { useState } from 'react';
import {
  BoltIcon,
  SearchIcon,
  CheckCircleIcon,
  ClockIcon,
  LocationIcon,
  LightbulbIcon,
  SparkleIcon,
  AlertCircleIcon,
  FileTextIcon,
} from '../common/Icons';
import { Badge } from '../common/Badge';
import { CHARGING_STATIONS, NETWORK_STATS, REQUIRED_STATION_PDFS } from '../../data/stationData';

export function ChargingView({ onConsultCopilot }) {
  const [filterProvince, setFilterProvince] = useState('all');
  const [filterPower, setFilterPower] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');

  const provinceOptions = [
    { id: 'all', label: 'Tất cả địa điểm' },
    { id: 'Nghệ An', label: 'Nghệ An (Vinh)' },
    { id: 'Hà Nội', label: 'Hà Nội' },
    { id: 'TP. Hồ Chí Minh', label: 'TP. Hồ Chí Minh' },
    { id: 'Đà Nẵng', label: 'Đà Nẵng' },
  ];

  const powerOptions = [
    { id: 'all', label: 'Tất cả công suất' },
    { id: 'Supercharge', label: 'Siêu nhanh 250kW+' },
    { id: 'DC 60kW', label: 'Nhanh DC 60kW' },
    { id: 'AC 11kW', label: 'Sạc chậm AC 11kW' },
  ];

  const filteredStations = CHARGING_STATIONS.filter((s) => {
    if (filterProvince !== 'all' && s.province !== filterProvince) return false;
    if (filterPower !== 'all' && !s.power_types.some((p) => p.includes(filterPower))) return false;
    if (
      searchQuery &&
      !s.name.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !s.address.toLowerCase().includes(searchQuery.toLowerCase())
    ) {
      return false;
    }
    return true;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* HEADER & OVERVIEW STATS */}
      <div className="card-dark" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, backgroundColor: 'rgba(255, 255, 255, 0.1)', padding: '4px 10px', borderRadius: 9999, marginBottom: 8 }}>
            <BoltIcon style={{ width: 13, height: 13, color: '#FFFFFF' }} />
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#E0E0E0' }}>
              Mạng lưới Trạm sạc V-GREEN Toàn quốc
            </span>
          </div>
          <h1 style={{ fontSize: '1.8rem', fontWeight: 800, color: '#FFFFFF' }}>
            Hạ tầng Trạm sạc V-GREEN 2026
          </h1>
          <p style={{ fontSize: '0.88rem', color: '#A3A3A3', marginTop: 4 }}>
            Mạng lưới trạm sạc xe điện lớn nhất Việt Nam, phủ sóng 63/63 tỉnh thành và 100% các tuyến cao tốc huyết mạch.
          </p>
        </div>

        {/* Stats Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 14, paddingTop: 16, borderTop: '1px solid rgba(255, 255, 255, 0.12)' }}>
          <div>
            <span style={{ fontSize: '0.72rem', color: '#888888', display: 'block' }}>Tổng cổng sạc:</span>
            <strong style={{ fontSize: '1.4rem', color: '#FFFFFF' }}>{NETWORK_STATS.total_ports}</strong>
          </div>
          <div>
            <span style={{ fontSize: '0.72rem', color: '#888888', display: 'block' }}>Phủ sóng tỉnh thành:</span>
            <strong style={{ fontSize: '1.4rem', color: '#FFFFFF' }}>{NETWORK_STATS.provinces_covered}</strong>
          </div>
          <div>
            <span style={{ fontSize: '0.72rem', color: '#888888', display: 'block' }}>Tuyến cao tốc:</span>
            <strong style={{ fontSize: '1.4rem', color: '#FFFFFF' }}>{NETWORK_STATS.highway_coverage}</strong>
          </div>
          <div>
            <span style={{ fontSize: '0.72rem', color: '#888888', display: 'block' }}>Trụ Supercharge:</span>
            <strong style={{ fontSize: '1.4rem', color: '#FFFFFF' }}>{NETWORK_STATS.supercharger_ports}</strong>
          </div>
          <div>
            <span style={{ fontSize: '0.72rem', color: '#888888', display: 'block' }}>Tỉ lệ sẵn sàng (Uptime):</span>
            <strong style={{ fontSize: '1.4rem', color: '#FFFFFF' }}>{NETWORK_STATS.uptime}</strong>
          </div>
        </div>
      </div>

      {/* FILTER & SEARCH BAR */}
      <div
        className="card-white"
        style={{
          padding: '16px 20px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 14,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#444444' }}>Khu vực:</span>
          {provinceOptions.map((opt) => (
            <button
              key={opt.id}
              className={`chip ${filterProvince === opt.id ? 'active' : ''}`}
              onClick={() => setFilterProvince(opt.id)}
              style={{ padding: '5px 12px', fontSize: '0.8rem' }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#444444' }}>Công suất:</span>
            {powerOptions.map((opt) => (
              <button
                key={opt.id}
                className={`chip ${filterPower === opt.id ? 'active' : ''}`}
                onClick={() => setFilterPower(opt.id)}
                style={{ padding: '5px 12px', fontSize: '0.8rem' }}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div style={{ position: 'relative', width: 200 }}>
            <SearchIcon style={{ position: 'absolute', left: 10, top: 9, width: 14, height: 14, color: '#888888' }} />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Tìm theo tên/địa chỉ..."
              style={{
                width: '100%',
                padding: '6px 10px 6px 30px',
                borderRadius: 9999,
                border: '1px solid #E5E5E5',
                fontSize: '0.8rem',
                outline: 'none',
              }}
            />
          </div>
        </div>
      </div>

      {/* STATIONS LIST & ADVISOR TIPS (2-COL) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 340px', gap: 24, alignItems: 'start' }}>
        {/* LEFT: STATIONS LIST OR EMPTY STATE WITH PDF REQUIREMENT */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {CHARGING_STATIONS.length === 0 ? (
            <div className="card-white" style={{ padding: '24px 28px', display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: '#F4F4F5', color: '#18181B', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <AlertCircleIcon style={{ width: 20, height: 20 }} />
                </div>
                <div>
                  <h3 style={{ fontSize: '1.05rem', fontWeight: 800, color: '#111827' }}>
                    Dữ liệu trạm sạc thực tế đang để trống
                  </h3>
                  <p style={{ fontSize: '0.82rem', color: '#6B7280', marginTop: 2 }}>
                    Hệ thống không dùng dữ liệu giả lập. Sẵn sàng tiếp nhận tệp dữ liệu PDF biểu phí & chính sách trạm sạc V-GREEN.
                  </p>
                </div>
              </div>

              {REQUIRED_STATION_PDFS.map((pdf) => (
                <div key={pdf.id} style={{ border: '1px solid #E5E7EB', borderRadius: 8, padding: '16px 20px', backgroundColor: '#F9FAFB' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <FileTextIcon style={{ width: 14, height: 14, color: '#52525B' }} />
                      <strong style={{ fontSize: '0.9rem', color: '#111827' }}>{pdf.title}</strong>
                    </div>
                    <Badge variant="highlight"><ClockIcon style={{ width: 11, height: 11, display: "inline", verticalAlign: "-1px", marginRight: 3 }} />{pdf.status}</Badge>
                  </div>

                  <div style={{ marginTop: 8, fontSize: '0.8rem', color: '#4B5563' }}>
                    <div>Tên file cần chuẩn bị: <code>{pdf.filename}</code></div>
                    <div>Mã định danh văn bản: <code>{pdf.document_id}</code></div>
                  </div>

                  <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid #E5E7EB' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#374151' }}>Nội dung cần có:</span>
                    <ul style={{ listStyle: 'none', paddingLeft: 0, margin: '6px 0 0 0', display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {pdf.required_contents.map((item, idx) => (
                        <li key={idx} style={{ fontSize: '0.78rem', color: '#6B7280', display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ color: '#71717A' }}>•</span>
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ))}
            </div>
          ) : filteredStations.length === 0 ? (
            <div className="card-white" style={{ padding: '32px 24px', textAlign: 'center', color: '#6B7280' }}>
              <p>Không tìm thấy trạm sạc nào phù hợp với bộ lọc hiện tại.</p>
            </div>
          ) : (
            filteredStations.map((st) => (
              <div
                key={st.id}
                className="card-white card-white-hover"
                style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 12 }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <Badge variant="highlight">{st.province}</Badge>
                      <span style={{ fontSize: '0.75rem', color: '#18181B', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <CheckCircleIcon style={{ width: 12, height: 12 }} /> {st.status}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: '#737373' }}>
                        <ClockIcon style={{ width: 11, height: 11, display: 'inline', marginRight: 3 }} />
                        {st.operating_hours}
                      </span>
                    </div>
                    <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#111111' }}>
                      {st.name}
                    </h3>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontSize: '0.78rem', color: '#737373' }}>Cổng sạc trống:</span>
                    <div style={{ fontSize: '1.1rem', fontWeight: 800, color: '#111111' }}>
                      {st.ports_available} / {st.ports_total}
                    </div>
                  </div>
                </div>

                <p style={{ fontSize: '0.85rem', color: '#555555' }}>
                  <LocationIcon style={{ width: 12, height: 12, display: "inline", verticalAlign: "-1px", marginRight: 3 }} />{st.address}
                </p>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#737373', marginRight: 4 }}>
                    Trụ sạc hỗ trợ:
                  </span>
                  {st.power_types.map((p, idx) => (
                    <span
                      key={idx}
                      style={{
                        padding: '3px 8px',
                        borderRadius: 4,
                        backgroundColor: '#ECECE9',
                        color: '#222222',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                      }}
                    >
                      <BoltIcon style={{ width: 11, height: 11, display: "inline", verticalAlign: "-1px", marginRight: 3 }} />{p}
                    </span>
                  ))}
                </div>

                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', paddingTop: 10, borderTop: '1px solid #F0F0EE', fontSize: '0.75rem', color: '#737373' }}>
                  <span style={{ fontWeight: 600 }}>Tiện ích lân cận:</span>
                  {st.amenities.map((a, idx) => (
                    <span key={idx} style={{ backgroundColor: '#F8F8F6', padding: '2px 6px', borderRadius: 4 }}>
                      {a}
                    </span>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>

        {/* RIGHT: ADVISOR CHARGING CHEAT-SHEET */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card-white" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <h3 style={{ fontSize: '0.92rem', fontWeight: 800, color: '#111111', borderBottom: '1px solid #F0F0EE', paddingBottom: 10 }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><LightbulbIcon style={{ width: 14, height: 14 }} /> BÍ QUYẾT TƯ VẤN SẠC PIN</span>
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontSize: '0.82rem', color: '#333333', lineHeight: 1.45 }}>
                <strong style={{ color: '#111111' }}>1. Khách ở chung cư không có trụ riêng:</strong>
                <p style={{ marginTop: 2, color: '#666666' }}>
                  Khuyên khách sạc tại trạm sạc nhanh gần cơ quan, siêu thị hoặc trạm V-GREEN 3S. Với quãng đường đi làm 20-30km/ngày, chỉ cần sạc 1 lần/tuần trong ~25 phút.
                </p>
              </div>

              <div style={{ fontSize: '0.82rem', color: '#333333', lineHeight: 1.45 }}>
                <strong style={{ color: '#111111' }}>2. Tính năng Cắm là Sạc (Plug & Charge):</strong>
                <p style={{ marginTop: 2, color: '#666666' }}>
                  Xe tự động nhận diện tài khoản VinFast, không cần quẹt thẻ hay thao tác phức tạp.
                </p>
              </div>

              <div style={{ fontSize: '0.82rem', color: '#333333', lineHeight: 1.45 }}>
                <strong style={{ color: '#111111' }}>3. Khuyến nghị duy trì pin bền:</strong>
                <p style={{ marginTop: 2, color: '#666666' }}>
                  Duy trì dung lượng hàng ngày từ 20% - 80%. Chỉ cần sạc 100% trước các chuyến đi xa dài ngày.
                </p>
              </div>
            </div>

            <button
              className="btn-primary"
              onClick={() => onConsultCopilot && onConsultCopilot('Tư vấn giải pháp sạc cho khách hàng chung cư và chính sách ưu đãi sạc 2026')}
              style={{ width: '100%', fontSize: '0.8rem', padding: '8px 12px', marginTop: 6 }}
            >
              <span>Tra cứu kịch bản với Copilot</span>
              <SparkleIcon style={{ width: 13, height: 13 }} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
