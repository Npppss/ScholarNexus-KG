import { useState, useEffect, useRef } from 'react';

export default function TimelineSlider({ minYear, maxYear, currentYear, onChange }) {
  const [isPlaying, setIsPlaying] = useState(false);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (isPlaying) {
      if (currentYear >= maxYear) {
        onChange(minYear);
      }
      
      intervalRef.current = setInterval(() => {
        onChange((prev) => {
          if (prev >= maxYear) {
             setIsPlaying(false);
             return maxYear;
          }
          return prev + 1;
        });
      }, 1200); // 1.2 detik per frame
    }
    return () => clearInterval(intervalRef.current);
  }, [isPlaying, maxYear, minYear, onChange]);

  if (!minYear || !maxYear || minYear === maxYear) {
    return (
      <div className="timeline-layout">
        <span className="timeline-label">Filter linimasa tahun tidak tersedia untuk dataset ini.</span>
      </div>
    );
  }

  return (
    <div className="timeline-layout">
      <button 
        className="btn"
        style={{ padding: '6px 12px', fontSize: '11px', minWidth: '60px', marginRight: '16px', borderRadius: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
        onClick={() => setIsPlaying(!isPlaying)}
        title={isPlaying ? "Jeda Animasi Linimasa" : "Jalankan Animasi Linimasa"}
      >
        {isPlaying ? (
          <>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="4" width="4" height="16" />
              <rect x="14" y="4" width="4" height="16" />
            </svg>
            <span>Jeda</span>
          </>
        ) : (
          <>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
            <span>Putar</span>
          </>
        )}
      </button>
      <div className="timeline-track">
        <span className="timeline-label">{minYear}</span>
        <input 
          type="range" 
          className="timeline-input" 
          min={minYear} 
          max={maxYear}
          value={currentYear}
          onChange={(e) => {
            setIsPlaying(false);
            onChange(parseInt(e.target.value, 10));
          }}
        />
        <span className="timeline-label">{maxYear}</span>
      </div>
      <div className="timeline-label" style={{ marginLeft: '16px', fontWeight: '600' }}>
        Tahun: &le; {currentYear}
      </div>
    </div>
  );
}
