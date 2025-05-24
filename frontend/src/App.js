import React, { useEffect, useState } from 'react';

function App() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    fetch('/api/health')
      .then(res => res.json())
      .then(data => setHealth(data))
      .catch(err => console.error('Error:', err));
  }, []);

  return (
    <div>
      <h1>Welcome to Payin App</h1>
      <p>This is a dummy frontend for basic use.</p>
      <div>
        <h2>API Health Status:</h2>
        <pre>{JSON.stringify(health, null, 2)}</pre>
      </div>
    </div>
  );
}

export default App;