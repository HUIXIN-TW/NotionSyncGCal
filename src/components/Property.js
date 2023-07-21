export function renderProperty(property, value, handleChange) {
    if (typeof value === 'boolean') {
      return (
        <select
          value={value.toString()}
          onChange={(e) => handleChange(property, e.target.value === 'true')}
        >
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      );
    } else if (typeof value === 'string') {
      return (
        <input
          type="text"
          value={value}
          onChange={(e) => handleChange(property, e.target.value)}
        />
      );
    } else if (typeof value === 'number') {
      return (
        <input
          type="number"
          value={value}
          onChange={(e) => handleChange(property, e.target.value)}
        />
      );
    } else if (Array.isArray(value)) {
      return (
        <ul>
          {value.map((item, index) => (
            <li key={index}>
              {renderProperty(index, item, handleChange)}
            </li>
          ))}
        </ul>
      );
    } else if (typeof value === 'object') {
      return (
        <ul>
          {Object.entries(value).map(([key, nestedValue]) => (
            <li key={key}>
              <strong>{key}:</strong> {renderProperty(key, nestedValue, handleChange)}
            </li>
          ))}
        </ul>
      );
    } else {
      return JSON.stringify(value);
    }
  }
  