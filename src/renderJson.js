import React, { useState, useEffect } from 'react';
import moment from 'moment-timezone';
import './renderJson.css';
import GCalItem from './components/GCalItem';
import AddGCalItem from './components/AddGCalItem';
import { renderProperty } from './components/Property';

function App() {
  const [jsonData, setJsonData] = useState({});
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch('./notion_setting.json');
        if (!response.ok) {
          throw new Error('Network response was not ok.');
        }
        const data = await response.json();
        setJsonData(data);
      } catch (error) {
        console.error('Error fetching JSON data:', error);
      }
    };
    fetchData();
  }, []);

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
    } else if (key === 'gcal_dic') {
      const updatedGCalDic = [...jsonData.gcal_dic, { [newKey]: newValue }];
      setJsonData((prevData) => ({
        ...prevData,
        gcal_dic: updatedGCalDic,
      }));
      setNewKey('');
      setNewValue('');
    } else {
      setJsonData((prevData) => ({
        ...prevData,
        [key]: newValue,
      }));
    }
  };

  const handleDeleteGCalItem = (index) => {
    // Remove the item at the specified index from the gcal_dic array
    setJsonData((prevData) => {
      const updatedGCalDic = [...prevData.gcal_dic];
      updatedGCalDic.splice(index, 1);
      return {
        ...prevData,
        gcal_dic: updatedGCalDic,
      };
    });
  };

  const handleNewKeyChange = (e) => {
    setNewKey(e.target.value);
  };

  const handleNewValueChange = (e) => {
    setNewValue(e.target.value);
  };

  const addNewGCalKeyValuePair = () => {
    // TO DO: Add new key-value pair to the same dictionary
    setJsonData((prevData) => {
      const updatedGCalDic = prevData.gcal_dic.map((item) => ({
        ...item,
        [newKey]: newValue,
      }));
      return {
        ...prevData,
        gcal_dic: updatedGCalDic,
      };
    });
    setNewKey('');
    setNewValue('');
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
    <div className="container">
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
           )  : key === 'gcal_dic' ? (
            <>
              <ul>
                {value.map((item, index) => (
                  <GCalItem
                    key={index}
                    item={item}
                    index={index}
                    handleValueChange={handleValueChange}
                    handleDeleteGCalItem={handleDeleteGCalItem}
                  />
                ))}
              </ul>
              <AddGCalItem
                newKey={newKey}
                newValue={newValue}
                handleNewKeyChange={handleNewKeyChange}
                handleNewValueChange={handleNewValueChange}
                addNewGCalKeyValuePair={addNewGCalKeyValuePair}
              />
            </>
          )  : (
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