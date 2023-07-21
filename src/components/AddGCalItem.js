// AddGCalItem.js
import React from 'react';

function AddGCalItem({ newKey, newValue, handleNewKeyChange, handleNewValueChange, addNewGCalKeyValuePair }) {
  return (
    <div  className="AddGCalItem">
      <strong>Calendar Name</strong>{' '}
      <input type="text" value={newKey} onChange={handleNewKeyChange} />
      <strong>Calendar ID :</strong>{' '}
      <input type="text" value={newValue} onChange={handleNewValueChange} />
      <button onClick={addNewGCalKeyValuePair}>Add</button>
    </div>
  );
}

export default AddGCalItem;