import React, { useState } from 'react';
import data from './data.json';
import moment from 'moment-timezone';
import './renderJson.css';

function App() {
  const [jsonData, setJsonData] = useState(data);
  
  const handleValueChange = (key, newValue) => {
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
    link.setAttribute('download', 'client.data.json'); // Set the same file name
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
            value ) :
            typeof value === 'string' ? (
             <input
               type="text"
               value={value}
               onChange={(e) => handleValueChange(key, e.target.value)}
             />
           ) : typeof value === 'boolean' ? (
             <select
               value={value.toString()}
               onChange={(e) => handleValueChange(key, e.target.value === 'true')}
             >
               <option value="true">true</option>
               <option value="false">false</option>
             </select>
           ) : (
             JSON.stringify(value)
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
