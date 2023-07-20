import React, { useState } from 'react';
import data from './data.json';
import moment from 'moment-timezone';
import './renderJson.css';

function renderProperty(property, value, handleChange) {
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
  }  else if (typeof value === 'number') {
    return (
      <input
        type="number"
        value={value}
        onChange={(e) => handleChange(property, e.target.value)}
      />
    );
  } 
  else if (Array.isArray(value)) {
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

function App() {
  const [jsonData, setJsonData] = useState(data);
  
  const handleValueChange = (key, newValue) => {
    if (key === 'description') {
      return;
    }
    if (key === 'timezone') {
      const selectedTimezone = newValue;
      const selectedTimezoneData = moment.tz(selectedTimezone);
      const updatedTimeCode = selectedTimezoneData.format('Z');
      setJsonData((prevData) => ({
        ...prevData,
        timezone: selectedTimezone,
        timecode: updatedTimeCode,
      }));
    } else {
      setJsonData((prevData) => ({
        ...prevData,
        [key]: newValue,
      }));
    }
  };
  
  const handleSave = () => {
    const jsonContent = JSON.stringify(jsonData, null, 2);
    const blob = new Blob([jsonContent], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'client.data.json'); 
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <h1>JSON Data:</h1>
      <p> Fill your personal setting</p>
      <ul>
        {Object.entries(jsonData).map(([key, value]) => (
           <li key={key}>
           <strong>{key}:</strong>{' '}
           {key === 'timezone' ? (
             <select
               value={value}
               onChange={(e) => handleValueChange(key, e.target.value)}
             >
               {moment.tz.names().map((zone) => (
                 <option key={zone} value={zone}>
                   {zone}
                 </option>
               ))}
             </select>
           ) : key === 'timecode' ? (
            value ) : (
              renderProperty(key, value, handleValueChange)
           )}
         </li>
        ))}
      </ul>
      <div className="container">
      <button className="save-button" onClick={handleSave}>Save</button>
      </div>
    </div>
  );
}

export default App;