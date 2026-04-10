export default function TimelineSlider({ minYear, maxYear, currentYear, onChange }) {
  if (!minYear || !maxYear || minYear === maxYear) {
    return (
      <div className="timeline-layout">
        <span className="timeline-label">Timeline filter unavailable for current dataset.</span>
      </div>
    );
  }

  return (
    <div className="timeline-layout">
      <div className="timeline-track">
        <span className="timeline-label">{minYear}</span>
        <input 
          type="range" 
          className="timeline-input" 
          min={minYear} 
          max={maxYear}
          value={currentYear}
          onChange={(e) => onChange(parseInt(e.target.value, 10))}
        />
        <span className="timeline-label">{maxYear}</span>
      </div>
      <div className="timeline-label" style={{ marginLeft: '16px', fontWeight: '600' }}>
        Filter: &le; {currentYear}
      </div>
    </div>
  );
}
