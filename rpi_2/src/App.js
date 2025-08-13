import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { initializeApp } from 'firebase/app';
import { getDatabase, ref, onValue, off } from 'firebase/database';
import './App.css'; // We'll create a separate CSS file

// Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyBaJvai7jj2Q_OTk2dJqNi7vuih00kryXk",
  authDomain: "smart-healthcare-3a0d6.firebaseapp.com",
  databaseURL: "https://smart-healthcare-3a0d6-default-rtdb.firebaseio.com",
  projectId: "smart-healthcare-3a0d6",
  storageBucket: "smart-healthcare-3a0d6.appspot.com",
  messagingSenderId: "376491385201",
  appId: "1:376491385201:web:f7fd6a69fb2a0e9c6e7890"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const database = getDatabase(app);

// Patient data configuration
const patients = [
  {
    id: 1,
    name: "Sharan Karthick",
    age: 65,
    Device_ID: "wearable_001", // Updated to match your Firebase device ID
    condition: "Stable",
    heartRateBase: 75,
    spO2Base: 97
  },
  {
    id: 2,
    name: "Maithreyan",
    age: 42,
    Device_ID: "105B",
    condition: "Critical",
    heartRateBase: 85,
    spO2Base: 94
  },
  {
    id: 3,
    name: "Ananya",
    age: 58,
    Device_ID: "310C",
    condition: "Stable",
    heartRateBase: 70,
    spO2Base: 98
  },
  {
    id: 4,
    name: "Zaahid Umar",
    age: 73,
    Device_ID: "117D",
    condition: "Under Observation",
    heartRateBase: 78,
    spO2Base: 95
  }
];

// Mock historical data (will be replaced with Firebase data for Patient 1)
const mockHistoricalData = {
  1: {
    heartRate: [
      { id: 1, date: '2025-04-27 09:15:22', value: 72, anomaly: false },
      { id: 2, date: '2025-04-27 10:30:45', value: 78, anomaly: false },
      { id: 3, date: '2025-04-27 11:45:12', value: 102, anomaly: true },
      { id: 4, date: '2025-04-27 12:30:38', value: 68, anomaly: false },
      { id: 5, date: '2025-04-27 13:15:20', value: 75, anomaly: false },
      { id: 6, date: '2025-04-27 14:25:50', value: 110, anomaly: true },
      { id: 7, date: '2025-04-27 15:40:33', value: 76, anomaly: false },
      { id: 8, date: '2025-04-27 16:55:10', value: 74, anomaly: false },
    ],
    spO2: [
      { id: 1, date: '2025-04-27 09:15:22', value: 98, anomaly: false },
      { id: 2, date: '2025-04-27 10:30:45', value: 97, anomaly: false },
      { id: 3, date: '2025-04-27 11:45:12', value: 92, anomaly: true },
      { id: 4, date: '2025-04-27 12:30:38', value: 98, anomaly: false },
      { id: 5, date: '2025-04-27 13:15:20', value: 96, anomaly: false },
      { id: 6, date: '2025-04-27 14:25:50', value: 91, anomaly: true },
      { id: 7, date: '2025-04-27 15:40:33', value: 97, anomaly: false },
      { id: 8, date: '2025-04-27 16:55:10', value: 98, anomaly: false },
    ]
  }
};

// For other patients, generate mock data
for (let i = 2; i <= 4; i++) {
  if (!mockHistoricalData[i]) {
    mockHistoricalData[i] = {
      heartRate: [],
      spO2: []
    };
    
    // Generate some mock data
    for (let j = 1; j <= 8; j++) {
      const date = new Date(2025, 3, 27, 9 + j, Math.floor(Math.random() * 60));
      const heartRateVal = patients[i-1].heartRateBase + Math.floor(Math.random() * 10) - 5;
      const spO2Val = patients[i-1].spO2Base + Math.floor(Math.random() * 4) - 2;
      const hrAnomaly = heartRateVal > 100 || heartRateVal < 60;
      const spO2Anomaly = spO2Val < 94;
      
      mockHistoricalData[i].heartRate.push({
        id: j,
        date: date.toISOString().slice(0, 10) + ' ' + date.toTimeString().slice(0, 8),
        value: heartRateVal,
        anomaly: hrAnomaly
      });
      
      mockHistoricalData[i].spO2.push({
        id: j,
        date: date.toISOString().slice(0, 10) + ' ' + date.toTimeString().slice(0, 8),
        value: spO2Val,
        anomaly: spO2Anomaly
      });
    }
  }
}

// Main App Component
function App() {
  const [selectedPatient, setSelectedPatient] = useState(null);
  
  const handleSelectPatient = (patientId) => {
    setSelectedPatient(patientId);
  };
  
  const handleBack = () => {
    setSelectedPatient(null);
  };
  
  return (
    <div className="app-container">
      {selectedPatient ? (
        <PatientDashboard patientId={selectedPatient} onBack={handleBack} />
      ) : (
        <PatientSelection onSelectPatient={handleSelectPatient} />
      )}
    </div>
  );
}

// Patient selection page component
function PatientSelection({ onSelectPatient }) {
  return (
    <div className="patient-selection">
      <header className="header">
        <h1>IoT Smart Healthcare Project</h1>
        <p>Real-time patient monitoring system</p>
      </header>
      
      <div className="patient-cards">
        {patients.map(patient => (
          <div key={patient.id} className="patient-card">
            <div className="patient-info">
              <h2>Patient {patient.id}</h2>
              
              <div className="patient-details">
                <div className="detail-row">
                  <span className="detail-label">Name:</span>
                  <span>{patient.name}</span>
                </div>
                
                <div className="detail-row">
                  <span className="detail-label">Age:</span>
                  <span>{patient.age}</span>
                </div>
                
                <div className="detail-row">
                  <span className="detail-label">Device_ID:</span>
                  <span>{patient.Device_ID}</span>
                </div>
                
                <div className="detail-row">
                  <span className="detail-label">Status:</span>
                  <span className={`status-badge ${patient.condition.toLowerCase().replace(' ', '-')}`}>
                    {patient.condition}
                  </span>
                </div>
              </div>
            </div>
            
            <div className="card-footer">
              <button 
                onClick={() => onSelectPatient(patient.id)}
                className="btn btn-primary"
              >
                View Details
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Patient dashboard component
function PatientDashboard({ patientId, onBack }) {
  const [page, setPage] = useState('realtime');
  const [path, setpath] = useState(null);
  const [heart_rate, setheart_rate] = useState([]);
  const [spo2, setspo2] = useState([]);
  const [alertsData, setAlertsData] = useState([]);
  const [timestamp, settimestamp] = useState(null);
  const [audioData, setAudioData] = useState([]);
  // Add new state for historical data from Firebase
  const [historicalHeartRate, setHistoricalHeartRate] = useState([]);
  const [historicalSpO2, setHistoricalSpO2] = useState([]);
  const [isLoadingHistorical, setIsLoadingHistorical] = useState(false);
  
  // Get patient data
  const patient = patients.find(p => p.id === patientId);
  
  // Firebase data fetching
  useEffect(() => {
    if (!patient) return;

    // For Patient 1, fetch real data from Firebase
    if (patient.id === 1) {
      const deviceRef = ref(database, `devices/${patient.Device_ID}`);
      
      onValue(deviceRef, (snapshot) => {
        const data = snapshot.val();
        if (data) {
          // Process vitals data
          const vitalsArray = [];
          const alertsArray = [];
          const audioArray = [];
          let latestImageUrl = null;
          
          // Process vitals
          if (data.vitals) {
            Object.entries(data.vitals).forEach(([id, vital]) => {
              const timestamp = new Date(vital.timestamp);
              vitalsArray.push({
                id,
                timestamp: timestamp.toLocaleTimeString(),
                rawTimestamp: vital.timestamp,
                heart_rate: vital.heart_rate,
                spo2: vital.spo2
              });
            });
            
            // Sort by timestamp
            vitalsArray.sort((a, b) => a.rawTimestamp - b.rawTimestamp);
            
            // Update state with the last 20 readings
            const recentVitals = vitalsArray.slice(-20);
            setheart_rate(recentVitals.map(v => ({ 
              timestamp: v.timestamp, 
              value: v.heart_rate 
            })));
            setspo2(recentVitals.map(v => ({ 
              timestamp: v.timestamp, 
              value: v.spo2 
            })));
            
            // Extract historical data - format for historical view
            // Use all available data points for historical view
            const formattedHeartRate = vitalsArray.map((v, index) => ({
              id: index + 1,
              date: new Date(v.rawTimestamp).toISOString().slice(0, 10) + ' ' + v.timestamp,
              value: v.heart_rate,
              anomaly: v.heart_rate > 100 || v.heart_rate < 60
            }));
            
            const formattedSpO2 = vitalsArray.map((v, index) => ({
              id: index + 1,
              date: new Date(v.rawTimestamp).toISOString().slice(0, 10) + ' ' + v.timestamp,
              value: v.spo2,
              anomaly: v.spo2 < 94
            }));
            
            setHistoricalHeartRate(formattedHeartRate);
            setHistoricalSpO2(formattedSpO2);
            
            // Set latest timestamp
            if (recentVitals.length > 0) {
              const latestVital = recentVitals[recentVitals.length - 1];
              settimestamp(new Date(latestVital.rawTimestamp));
            }
          }
          
          // Process alerts
          if (data.alerts) {
            Object.entries(data.alerts).forEach(([id, alert]) => {
              alertsArray.push({
                id,
                timestamp: new Date(alert.timestamp).toLocaleString(),
                type: alert.alert_type,
                source: alert.source,
                value: alert.value,
                threshold: alert.threshold,
                keyword: alert.keyword,
                confidence: alert.confidence,
                anomaly_score: alert.anomaly_score
              });
            });
            
            // Sort alerts by timestamp (newest first)
            alertsArray.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            setAlertsData(alertsArray);
          }
          
          // Process audio data
          if (data.audio) {
            Object.entries(data.audio).forEach(([id, audio]) => {
              audioArray.push({
                id,
                timestamp: new Date(audio.timestamp).toLocaleString(),
                filepath: audio.filepath,
                processed: audio.processed,
                keyword_detected: audio.keyword_detected,
                keyword: audio.keyword,
                confidence: audio.confidence
              });
            });
            
            // Sort audio by timestamp (newest first)
            audioArray.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            setAudioData(audioArray);
          }
          
          // Get latest image if any
          if (data.images) {
            const images = Object.values(data.images);
            if (images.length > 0) {
              // Sort by timestamp and get the latest
              const latestImage = images.sort((a, b) => b.timestamp - a.timestamp)[0];
              // Use a placeholder for the image
              latestImageUrl = `/api/placeholder/320/240`;
              setpath(latestImageUrl);
            }
          }
        }
      });
      
      return () => {
        // Cleanup
        off(deviceRef);
      };
    } else {
      // For other patients, use mock data
      setheart_rate(generateMockData(20, patient.heartRateBase, 10));
      setspo2(generateMockData(20, patient.spO2Base, 4));
      
      // Use mock historical data
      setHistoricalHeartRate(mockHistoricalData[patient.id].heartRate);
      setHistoricalSpO2(mockHistoricalData[patient.id].spO2);
      
      // Start mock data simulation
      const interval = setInterval(() => {
        setheart_rate(prevData => {
          const newData = [...prevData];
          const timestamp = new Date();
          newData.push({
            timestamp: timestamp.toLocaleTimeString(),
            value: patient.heartRateBase + Math.random() * 10 - 5
          });
          if (newData.length > 20) newData.shift();
          return newData;
        });
        
        setspo2(prevData => {
          const newData = [...prevData];
          const timestamp = new Date();
          newData.push({
            timestamp: timestamp.toLocaleTimeString(),
            value: patient.spO2Base + Math.random() * 4 - 2
          });
          if (newData.length > 20) newData.shift();
          return newData;
        });
        
        settimestamp(new Date());
        
        // Simulate voice trigger for image capture
        if (Math.random() > 0.95) {
          setpath(`/api/placeholder/320/240`);
        }
      }, 2000);
      
      return () => clearInterval(interval);
    }
  }, [patient, database]);
  
  // Calculate current values for stats
  const currentHeartRate = heart_rate.length > 0 
    ? Math.round(heart_rate[heart_rate.length - 1].value) 
    : 0;
    
  const currentSpO2 = spo2.length > 0 
    ? Math.round(spo2[spo2.length - 1].value) 
    : 0;
  
  // Generate mock data function (used for non-Firebase patients)
  const generateMockData = (count, base, variance) => {
    const data = [];
    let timestamp = new Date();
    
    for (let i = 0; i < count; i++) {
      timestamp = new Date(timestamp.getTime() - 1000);
      data.unshift({
        timestamp: timestamp.toLocaleTimeString(),
        value: base + Math.random() * variance - variance/2
      });
    }
    return data;
  };
  
  const downloadData = (type) => {
    if (!patient) return;
    
    let data;
    
    if (patient.id === 1 && type === 'heartrate') {
      // Use real Firebase data for patient 1
      data = historicalHeartRate;
    } else if (patient.id === 1 && type === 'spo2') {
      // Use real Firebase data for patient 1
      data = historicalSpO2;
    } else {
      // Use mock historical data for other patients
      data = type === 'heartrate' 
        ? mockHistoricalData[patient.id].heartRate 
        : mockHistoricalData[patient.id].spO2;
    }
      
    const csvContent = "data:text/csv;charset=utf-8," + 
      "ID,Date,Value,Anomaly\n" + 
      data.map(row => `${row.id},${row.date},${row.value},${row.anomaly}`).join("\n");
    
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `patient${patient.id}_${type}_data.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };
  
  if (!patient) return <div>Patient not found</div>;
  
  // Use the actual data from Firebase for patient 1, otherwise use mock data
  const displayHeartRateData = patient.id === 1 ? historicalHeartRate : mockHistoricalData[patient.id].heartRate;
  const displaySpO2Data = patient.id === 1 ? historicalSpO2 : mockHistoricalData[patient.id].spO2;
  
  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <button 
          onClick={onBack}
          className="btn btn-secondary"
        >
          ← Back
        </button>
        <div>
          <h1>IoT Smart Healthcare Project</h1>
          <h2>
            Patient {patient.id}: {patient.name}
            {patient.id === 1 && <span className="firebase-badge">Firebase Connected</span>}
          </h2>
        </div>
      </header>
      
      <div className="tab-navigation">
        <button 
          onClick={() => setPage('realtime')} 
          className={`tab-button ${page === 'realtime' ? 'active' : ''}`}
        >
          Real-time Monitoring
        </button>
        <button 
          onClick={() => setPage('history')} 
          className={`tab-button ${page === 'history' ? 'active' : ''}`}
        >
          Historical Data
        </button>
        {patient.id === 1 && (
          <button 
            onClick={() => setPage('alerts')} 
            className={`tab-button ${page === 'alerts' ? 'active' : ''}`}
          >
            Alerts & Notifications
          </button>
        )}
        {patient.id === 1 && (
          <button 
            onClick={() => setPage('audio')} 
            className={`tab-button ${page === 'audio' ? 'active' : ''}`}
          >
            Audio Analysis
          </button>
        )}
      </div>
      
      {page === 'realtime' ? (
        <div>
          {/* Patient Info */}
          <div className="card patient-info-card">
            <h2>Patient Information</h2>
            <div className="info-grid">
              <div>
                <strong>Name:</strong> {patient.name}
              </div>
              <div>
                <strong>Age:</strong> {patient.age}
              </div>
              <div>
                <strong>Device_ID:</strong> {patient.Device_ID}
              </div>
              <div>
                <strong>Status:</strong> 
                <span className={`status-badge ${patient.condition.toLowerCase().replace(' ', '-')}`}>
                  {patient.condition}
                </span>
              </div>
            </div>
          </div>
          
          {/* Stats Cards */}
          <div className="stats-cards">
            <div className="stat-card">
              <h3>Current Heart Rate</h3>
              <div className="stat-value">{currentHeartRate} BPM</div>
              <div className="stat-status">
                {currentHeartRate > 100 || currentHeartRate < 60 ? "Outside normal range" : "Normal range"}
              </div>
            </div>
            
            <div className="stat-card">
              <h3>Current SpO2 Level</h3>
              <div className="stat-value">{currentSpO2}%</div>
              <div className="stat-status">
                {currentSpO2 < 94 ? "Below normal range" : "Normal range"}
              </div>
            </div>
            
            <div className="stat-card">
              <h3>Latest Update</h3>
              <div className="stat-value">
                {timestamp ? 
                  (new Date().getTime() - timestamp.getTime() < 10000 ? 
                    "Just now" : 
                    timestamp.toLocaleTimeString()) : 
                  "N/A"}
              </div>
              <div className="stat-status">
                {patient.id === 1 ? "Real-time Firebase data" : "Auto-refreshing every 2 seconds"}
              </div>
            </div>
          </div>
          
          {/* Heart Rate Chart */}
          <div className="card chart-card">
            <h2>Heart Rate (BPM)</h2>
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={heart_rate}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" />
                  <YAxis domain={[60, 120]} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="value" stroke="#ef4444" name="Heart Rate" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          
          {/* SpO2 Chart */}
          <div className="card chart-card">
            <h2>Blood Oxygen (SpO2 %)</h2>
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={spo2}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" />
                  <YAxis domain={[90, 100]} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="value" stroke="#3b82f6" name="SpO2" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          
          {/* Image Capture */}
          <div className="card">
            <h2>Captured Image</h2>
            {path ? (
              <div className="image-container">
                <img 
                  src={path} 
                  alt="Captured image" 
                  className="captured-image" 
                />
                <p className="image-caption">
                  {patient.id === 1 ? 
                    "Latest image from device" : 
                    "Image captured after voice trigger \"ouch\" or \"ahh\""}
                </p>
              </div>
            ) : (
              <div className="no-image">
                <div className="placeholder-image">
                  <p>No image available</p>
                </div>
                <p className="image-caption">
                  {patient.id === 1 ? 
                    "Waiting for device image..." : 
                    "Say \"ouch\" or \"ahh\" to capture image"}
                </p>
              </div>
            )}
          </div>
        </div>
      ) : page === 'alerts' ? (
        <div className="card">
          <h2>Alerts & Notifications</h2>
          
          {alertsData.length > 0 ? (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Type</th>
                    <th>Source</th>
                    <th>Value</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {alertsData.map((alert) => (
                    <tr key={alert.id}>
                      <td>{alert.timestamp}</td>
                      <td>
                        <span className={`alert-badge ${alert.type}`}>
                          {alert.type ? (alert.type.charAt(0).toUpperCase() + alert.type.slice(1)) : 'Unknown'}
                        </span>
                      </td>
                      <td>{alert.source || 'N/A'}</td>
                      <td>{alert.value || alert.keyword || 'N/A'}</td>
                      <td>
                        {alert.type === 'threshold' && alert.threshold && 
                          `Threshold: ${alert.threshold}`}
                        {alert.type === 'keyword' && alert.keyword && 
                          `Keyword detected: "${alert.keyword}" (${(alert.confidence * 100).toFixed(1)}% confidence)`}
                        {alert.type === 'anomaly' && alert.anomaly_score && 
                          `Anomaly score: ${alert.anomaly_score.toFixed(2)}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">
              No alerts found for this patient
            </div>
          )}
        </div>
      ) : page === 'audio' ? (
        <div className="card">
          <h2>Audio Analysis</h2>
          
          {audioData.length > 0 ? (
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Filepath</th>
                    <th>Processed</th>
                    <th>Keyword</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {audioData.map((audio) => (
                    <tr key={audio.id}>
                      <td>{audio.timestamp}</td>
                      <td className="filepath">{audio.filepath}</td>
                      <td>
                        <span className={`status-badge ${audio.processed ? 'processed' : 'pending'}`}>
                          {audio.processed ? 'Processed' : 'Pending'}
                        </span>
                      </td>
                      <td>
                        {audio.keyword_detected ? (
                          <span className="keyword-badge">
                            {audio.keyword || 'Unknown'}
                          </span>
                        ) : 'None'}
                      </td>
                      <td>
                        {audio.keyword_detected && audio.confidence ? 
                          `${(audio.confidence * 100).toFixed(1)}%` : 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">
              No audio data found for this patient
            </div>
          )}
        </div>
      ) : (
        <div>
          <div className="card history-card">
            <h2>Historical Data</h2>
            {patient.id === 1 && (
              <div className="data-source-info">
                <span className="firebase-badge">Firebase Data</span>
                <p>Showing actual historical data from Firebase database</p>
              </div>
            )}
            
            <div className="history-grid">
              <div className="history-section">
                <h3>Heart Rate History</h3>
                <div className="table-container">
                  {displayHeartRateData.length > 0 ? (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Value (BPM)</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {displayHeartRateData.map(entry => (
                          <tr key={entry.id}>
                            <td>{entry.date}</td>
                            <td>{Math.round(entry.value)}</td>
                            <td>
                              <span className={`status-badge ${entry.anomaly ? 'anomaly' : 'normal'}`}>
                                {entry.anomaly ? 'Anomaly' : 'Normal'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="loading-state">
                      <p>Loading historical data...</p>
                    </div>
                  )}
                </div>
                <button
                  onClick={() => downloadData('heartrate')}
                  className="btn btn-primary download-btn"
                  disabled={displayHeartRateData.length === 0}
                >
                  Download Heart Rate Data (CSV)
                </button>
              </div>
              
              <div className="history-section">
                <h3>SpO2 History</h3>
                <div className="table-container">
                  {displaySpO2Data.length > 0 ? (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Date</th>
                          <th>Value (%)</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {displaySpO2Data.map(entry => (
                          <tr key={entry.id}>
                            <td>{entry.date}</td>
                            <td>{Math.round(entry.value)}</td>
                            <td>
                              <span className={`status-badge ${entry.anomaly ? 'anomaly' : 'normal'}`}>
                                {entry.anomaly ? 'Anomaly' : 'Normal'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="loading-state">
                      <p>Loading historical data...</p>
                    </div>
                  )}
                </div>
                <button
                  onClick={() => downloadData('spo2')}
                  className="btn btn-primary download-btn"
                  disabled={displaySpO2Data.length === 0}
                >
                  Download SpO2 Data (CSV)
                </button>
              </div>
            </div>
          </div>
          
          {/* Historical Charts */}
          <div className="history-charts">
            <div className="card chart-card">
              <h2>Heart Rate Historical Trend</h2>
              <div className="chart-container">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={displayHeartRateData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={false} />
                    <YAxis domain={[50, 120]} />
                    <Tooltip />
                    <Legend />
                    <Line 
                      type="monotone" 
                      dataKey="value" 
                      stroke="#ef4444" 
                      name="Heart Rate" 
                      strokeWidth={2}
                      dot={{ 
                        stroke: '#ef4444', 
                        r: 4, 
                        strokeWidth: 2,
                        fill: data => (data.anomaly ? '#ef4444' : '#fff')  
                      }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
            
            <div className="card chart-card">
              <h2>SpO2 Historical Trend</h2>
              <div className="chart-container">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={displaySpO2Data}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={false} />
                    <YAxis domain={[90, 100]} />
                    <Tooltip />
                    <Legend />
                    <Line 
                      type="monotone" 
                      dataKey="value" 
                      stroke="#3b82f6" 
                      name="SpO2" 
                      strokeWidth={2}
                      dot={{ 
                        stroke: '#3b82f6', 
                        r: 4, 
                        strokeWidth: 2,
                        fill: data => (data.anomaly ? '#3b82f6' : '#fff')  
                      }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
