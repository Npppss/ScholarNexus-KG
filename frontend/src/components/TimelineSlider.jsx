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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlaying, maxYear, minYear, onChange]);

  if (!minYear || !maxYear || minYear === maxYear) {
    return (
      <div className="timeline-layout">
        <span className="timeline-label">Timeline filter unavailable for current dataset.</span>
      </div>
    );
  }

  return (
    <div className="timeline-layout">
      <button 
        className="btn"
        style={{ padding: '4px 12px', fontSize: '12px', minWidth: '32px', marginRight: '16px', borderRadius: '50%' }}
        onClick={() => setIsPlaying(!isPlaying)}
        title={isPlaying ? "Pause Animation" : "Play Timeline Animation"}
      >
        {isPlaying ? '⏸' : '▶'}
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
            setIsPlaying(false); // Stop playing if user manually drags
            onChange(parseInt(e.target.value, 10));
          }}
        />
        <span className="timeline-label">{maxYear}</span>
      </div>
      <div className="timeline-label" style={{ marginLeft: '16px', fontWeight: '600' }}>
        Filter: &le; {currentYear}
      </div>
    </div>
  );
}
