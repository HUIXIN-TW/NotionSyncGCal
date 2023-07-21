// GCalItem.js
import React from 'react';

function GCalItem({ item, index, handleValueChange, handleDeleteGCalItem }) {
  return (
    <div className="GCalItem">
    <li key={index}>
      {Object.entries(item).map(([itemKey, itemValue]) => (
        <div key={itemKey}>
          <strong>{itemKey}:</strong>{' '}
          <input
            type="text"
            value={itemValue}
            onChange={(e) =>
              handleValueChange('gcal_dic', [
                ...item.slice(0, index),
                { ...item, [itemKey]: e.target.value },
                ...item.slice(index + 1),
              ])
            }
          />
        </div>
      ))}
      <button  onClick={() => handleDeleteGCalItem(index)}>Delete</button>
    </li>
    </div>
  );
}

export default GCalItem;