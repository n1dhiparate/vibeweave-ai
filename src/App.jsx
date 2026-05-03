import { useEffect, useState } from 'react';
import { supabase } from './supabaseClient';

const API = import.meta.env.PROD ? '' : (import.meta.env.VITE_API_URL || 'http://localhost:5000');

function App() {
  const [session, setSession] = useState(null);
  const [userProfile, setUserProfile] = useState(null);
  const [playlists, setPlaylists] = useState([]);
  const [currentPlaylist, setCurrentPlaylist] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // Auth Form State
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  // Generation Form State
  const [mood, setMood] = useState('');
  const [context, setContext] = useState('late night');
  const [energy, setEnergy] = useState('medium');
  const [intent, setIntent] = useState('relax');

  const [visitCtr, setVisitCtr] = useState('000000');

  useEffect(() => {
    let v = parseInt(localStorage.getItem('mw_v') || '0') + 1;
    localStorage.setItem('mw_v', v);
    setVisitCtr(String(v).padStart(6, '0'));

    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      if (session) fetchMe(session);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (session) fetchMe(session);
      else {
        setUserProfile(null);
        setPlaylists([]);
      }
    });

    const urlParams = new URLSearchParams(window.location.search);
    const spotifyParam = urlParams.get('spotify');
    if (spotifyParam === 'connected') {
      showErr('spotify connected !! your next playlist will use your library');
      window.history.replaceState({}, document.title, '/');
    } else if (spotifyParam && spotifyParam.startsWith('error')) {
      showErr('spotify connection failed. check your redirect uri and try again');
      window.history.replaceState({}, document.title, '/');
    }

    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    const chars=['✿','♡','★','✦','♪','♥','✸','❀'];
    const colors=['#ff69b4','#87ceeb','#c490ff','#ffd060','#7de8b8','#ff9ec5'];
    
    const tick = () => {
      const layer = document.getElementById('sparks');
      if(!layer) return;
      const el = document.createElement('div');
      el.className = 'spk';
      el.textContent = chars[Math.floor(Math.random()*chars.length)];
      el.style.left = Math.random()*100 + 'vw';
      el.style.top = Math.random()*90 + 'vh';
      el.style.color = colors[Math.floor(Math.random()*colors.length)];
      el.style.animationDelay = '0s';
      el.style.fontSize = '10px';
      layer.appendChild(el);
      setTimeout(()=>el.remove(), 2000);
    };
    const interval = setInterval(tick, 1200);
    return () => clearInterval(interval);
  }, []);

  const triggerBurst = () => {
    const chars=['✿','♡','★','✦','♪','♥','✸','❀'];
    const colors=['#ff69b4','#87ceeb','#c490ff','#ffd060','#7de8b8','#ff9ec5'];
    const layer = document.getElementById('sparks');
    if(!layer) return;
    for(let i=0;i<22;i++){
      const el=document.createElement('div');
      el.className='spk';
      el.textContent=chars[Math.floor(Math.random()*chars.length)];
      el.style.left=Math.random()*100+'vw';
      el.style.top=Math.random()*80+'vh';
      el.style.color=colors[Math.floor(Math.random()*colors.length)];
      el.style.animationDelay=Math.random()*0.8+'s';
      el.style.fontSize=(10+Math.random()*14)+'px';
      layer.appendChild(el);
      setTimeout(()=>el.remove(),2400);
    }
  };

  const appApi = async (path, opts = {}) => {
    const headers = { 'Content-Type': 'application/json' };
    if (session) {
      headers['Authorization'] = `Bearer ${session.access_token}`;
    }
    const r = await fetch(`${API}${path}`, {
      ...opts,
      headers: { ...headers, ...(opts.headers || {}) }
    });
    const j = await r.json().catch(()=>({status:'error', message:'bad server response'}));
    if (!r.ok || j.status === 'error') throw new Error(j.message || 'something went wrong :(');
    return j;
  };

  const fetchMe = async (activeSession) => {
    try {
      const data = await appApi('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${activeSession.access_token}` }
      });
      setUserProfile(data.user);
      fetchPlaylists(activeSession);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchPlaylists = async (activeSession) => {
    try {
      const data = await appApi('/api/playlists', {
        headers: { 'Authorization': `Bearer ${activeSession.access_token}` }
      });
      setPlaylists(data.playlists || []);
    } catch (err) {
      console.error(err);
    }
  };

  const handleRegister = async () => {
    setError(null);
    const { data, error } = await supabase.auth.signUp({ email, password });
    if (error) showErr(error.message);
    else {
        showErr("Success! You are now registered and logged in ♡");
        triggerBurst();
    }
  };

  const handleLogin = async () => {
    setError(null);
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) showErr(error.message);
    else triggerBurst();
  };

  const handleLogout = async () => {
    await supabase.auth.signOut();
    clearAll();
  };

  const connectSpotify = async () => {
    try {
      const data = await appApi('/api/spotify/auth-url');
      window.location.href = data.url;
    } catch (e) {
      showErr(e.message);
    }
  };

  const disconnectSpotify = async () => {
    try {
      await appApi('/api/spotify/disconnect', { method: 'POST', body: '{}' });
      fetchMe(session);
    } catch (e) {
      showErr(e.message);
    }
  };

  const showErr = (m) => setError(m);
  const hideErr = () => setError(null);

  const clearAll = () => {
    setMood('');
    setCurrentPlaylist(null);
    hideErr();
  };

  const generate = async () => {
    if(!session){showErr('log in first so i can save ur playlist');return;}
    if(!mood){showErr('tell me how ur feeling first !!');return;}
    setLoading(true);
    hideErr();
    setCurrentPlaylist(null);
    try {
      const data = await appApi('/api/generate-playlist', {
        method: 'POST',
        body: JSON.stringify({ mood, context, energy, intent })
      });
      setCurrentPlaylist(data.playlist);
      triggerBurst();
      fetchPlaylists(session);
    } catch (e) {
      showErr(e.message.includes('fetch') ? 'cant reach backend !! make sure flask is running' : e.message);
    } finally {
      setLoading(false);
    }
  };

  const esc = (s) => String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  return (
    <>
      <div className="sparks-layer" id="sparks"></div>

      <div className="topbar">
        <span className="topbar-inner">♥ welcome to moodwave ♥ tell me how ur feeling &amp; i'll make u the perfect playlist ♥ music heals everything ♥ best viewed with headphones on ♥ est. 2026 ♥ welcome to moodwave ♥ tell me how ur feeling &amp; i'll make u the perfect playlist ♥</span>
      </div>

      <div className="header">
        <div>
          <div className="site-title">✿ moodwave ✿</div>
          <div className="site-subtitle">playlists 4 ur heart &nbsp;&nbsp;♪&nbsp; made w/ love</div>
        </div>
        <div className="header-decos">
          <span className="pix-badge blink">✦ ONLINE ✦</span>
          <img className="header-icon bounce" src="/assets/headphones.png" alt="Pink headphones"/>
        </div>
      </div>
      <div className="starrow"></div>

      <div className="wrap">
        {/* LEFT COL */}
        <div className="col">
          <div className="bevel">
            <div className="bh pink">✦ navigation</div>
            <div className="bb" style={{padding: '7px'}}>
              <a className="navbtn">♥ home</a>
              <a className="navbtn">✿ about</a>
              <a className="navbtn">★ diary</a>
              <a className="navbtn">♪ credits</a>
            </div>
          </div>

          <div className="dot-box">
            <div className="bh pink">♪ now playing...</div>
            <div className="vinyl-wrap">
              <div className="vinyl"><div className="vinyl-label"></div></div>
              <div className="np-text" id="np-song">
                {currentPlaylist && currentPlaylist.songs?.length > 0 
                  ? `${currentPlaylist.songs[0].title} — ${currentPlaylist.songs[0].artist}`
                  : 'waiting for ur mood'}
              </div>
              <div className="np-text" style={{fontSize: '8px', marginTop: '1px'}}>♪ moodwave fm</div>
            </div>
            <div className="hearts">♥ ♡ ♥ ♡ ♥</div>
          </div>

          <div className="blue-box">
            <div className="bh blue">✦ status</div>
            <div className="bb">
              <div style={{fontSize: '9.5px', lineHeight: '2.1'}}>
                <span style={{color: '#ff69b4'}}>mood:</span> <span className="blink" style={{color: '#cc1177'}}>♥ online</span><br/>
                <span style={{color: '#87ceeb'}}>ai:</span> <span style={{color: '#2070a0'}}>ready ✓</span><br/>
                <span style={{color: '#c490ff'}}>vibes:</span> <span style={{color: '#7030b0'}}>loading...</span>
              </div>
              <div style={{height: '3px', background: 'repeating-linear-gradient(90deg,#ff69b4 0,#ff69b4 4px,#87ceeb 4px,#87ceeb 8px,#c490ff 8px,#c490ff 12px)', margin: '5px 0'}}></div>
              <div style={{fontSize: '8.5px', color: '#a06080'}}>
                site by <span style={{color: '#ff69b4', fontWeight: 800}}>Nidhi Parate</span> ✦<br/>
              </div>
            </div>
          </div>

          <div className="lav-box">
            <div className="bh lav">♡ my badges</div>
            <div className="bb" style={{textAlign: 'center', padding: '6px 5px'}}>
              <span className="blinkie pk">♥ music</span>
              <span className="blinkie gn">dev</span>
              <span className="blinkie pk">coder</span>
              <span className="blinkie bl">vibes</span>
            </div>
          </div>

          <div className="dot-box">
            <div className="bh yellow">★ visitors</div>
            <div className="bb" style={{textAlign: 'center'}}>
              <span className="counter" id="visit-ctr">{visitCtr}</span>
              <div style={{fontSize: '8px', color: '#a06080', marginTop: '2px'}}>thank u 4 visiting ♡</div>
            </div>
          </div>
        </div>

        {/* MAIN CENTER */}
        <div className="main">
          <div className="auth-box">
            <div className="bh blue" style={{margin: '-10px -10px 8px'}}>account</div>
            {!session ? (
              <div id="auth-guest">
                <div className="auth-note">log in or make an account to generate and save playlists</div>
                <div className="auth-row">
                  <input className="auth-input" value={email} onChange={e => setEmail(e.target.value)} placeholder="email" />
                  <input className="auth-input" value={password} onChange={e => setPassword(e.target.value)} type="password" placeholder="password" />
                </div>
                <div className="auth-actions">
                  <button className="clr-btn" onClick={handleRegister}>register</button>
                  <button className="gen-btn" onClick={handleLogin}>login</button>
                </div>
              </div>
            ) : (
              <div id="auth-userbox">
                <div className="auth-note">signed in as</div>
                <span className="user-pill">{userProfile?.email || session.user.email}</span>
                <div className="auth-note" style={{marginTop: '5px'}}>
                  {userProfile?.spotify_connected 
                    ? `spotify connected: ${userProfile.spotify_display_name || 'ready'}`
                    : 'spotify not connected'}
                </div>
                <div className="auth-actions">
                  {!userProfile?.spotify_connected ? (
                    <button className="gen-btn" onClick={connectSpotify}>connect spotify</button>
                  ) : (
                    <button className="clr-btn" onClick={disconnectSpotify}>disconnect spotify</button>
                  )}
                  <button className="clr-btn" onClick={handleLogout}>logout</button>
                </div>
              </div>
            )}
          </div>

          <div className="mood-box">
            <div className="mood-box-inner">
              <textarea rows="3" value={mood} onChange={e => setMood(e.target.value)} onKeyDown={e => {if(e.key === 'Enter' && !e.shiftKey) {e.preventDefault(); generate();}}} placeholder="i just got home after a long day, it's raining outside and i wanna cry a lil but in a good way..."></textarea>
              <div className="sel-grid">
                <div className="sel-group">
                  <div className="sel-lbl">✦ context</div>
                  <select value={context} onChange={e => setContext(e.target.value)}>
                    <option value="late night">late night</option>
                    <option value="night drive">night drive</option>
                    <option value="morning">morning</option>
                    <option value="studying">studying</option>
                    <option value="gym">gym</option>
                    <option value="commute">commute</option>
                    <option value="chill at home">home ♡</option>
                  </select>
                </div>
                <div className="sel-group">
                  <div className="sel-lbl">★ energy</div>
                  <select value={energy} onChange={e => setEnergy(e.target.value)}>
                    <option value="low">low ~ drift</option>
                    <option value="medium">med ~ flow</option>
                    <option value="high">high ~ push</option>
                  </select>
                </div>
                <div className="sel-group">
                  <div className="sel-lbl">♡ intent</div>
                  <select value={intent} onChange={e => setIntent(e.target.value)}>
                    <option value="focus">focus</option>
                    <option value="relax">relax</option>
                    <option value="hype">hype</option>
                    <option value="reflect">reflect</option>
                    <option value="sleep">sleep zzz</option>
                  </select>
                </div>
              </div>
              <div className="gen-row">
                <button className="clr-btn" onClick={clearAll}>✕ clear</button>
                <button className="gen-btn" onClick={generate} disabled={loading}>
                  {!loading ? <span id="btn-txt">✿ generate playlist ♪</span> : <span id="btn-spin"><span className="sp"></span>generating...</span>}
                </button>
              </div>
            </div>
          </div>

          {error && <div className="err-box" style={{display: 'block'}}>{error}</div>}

          {currentPlaylist && (
            <div id="output" style={{display: 'block'}}>
              <div className="pl-header-box">
                <div className="pl-title">✿ {currentPlaylist.playlist_name || 'ur playlist'} ✿</div>
                <div className="pl-desc">{currentPlaylist.theme_description}</div>
                <div className="pl-curve">{currentPlaylist.energy_curve}</div>
                <div className="pl-tags-row">
                  {(currentPlaylist.tags || []).map((t, i) => (
                    <span key={i} className={`blinkie ${['pk','bl','lv','gn'][i%4]}`}>{t}</span>
                  ))}
                </div>
              </div>
              <div className="track-list">
                {(currentPlaylist.songs || []).map((song, i) => (
                  <div className="track" style={{animationDelay: `${i*45}ms`}} key={i}>
                    <div className="t-num">{String(i+1).padStart(2,'0')}</div>
                    {song.album_art && <img className="t-cover" src={song.album_art} alt="cover" />}
                    <div className="t-info">
                      <div className="t-title">{song.title}</div>
                      <div className="t-artist">♪ {song.artist}</div>
                      {song.reason && <div className="t-reason">{song.reason}</div>}
                      {song.spotify_url && <a className="t-link" href={song.spotify_url} target="_blank" rel="noopener">open spotify</a>}
                    </div>
                    <div className={`edot ${(song.energy||'').toLowerCase()}`}></div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>

        {/* RIGHT COL */}
        <div className="col">
          <div className="dot-box">
            <div className="bh pink">♡ hi there!</div>
            <div className="bb" style={{fontFamily: "'Kosugi Maru',sans-serif", fontSize: '9.5px', lineHeight: 1.75}}>
              ok so!! welcome to moodwave ✿<br/>
              tell me how ur feeling &amp; i'll make u the <span style={{color: '#ff69b4', fontWeight: 700}}>perfect</span> playlist ♪
              <div style={{height: '2px', background: '#ffb6de', margin: '5px 0'}}></div>
              <span style={{color: '#c490ff'}}>fav artists:</span><br/>
              frank ocean, bon iver, joji, the xx
              <div style={{textAlign: 'right', fontSize: '8px', color: '#d090b0', marginTop: '3px'}}>updated: today ♡</div>
            </div>
          </div>

          <div className="bevel" style={{borderColor: '#87ceeb', borderTopColor: '#c0e8ff', borderLeftColor: '#c0e8ff', borderBottomColor: '#3a8ab0', borderRightColor: '#3a8ab0'}}>
            <div className="bh blue">✦ how 2 use</div>
            <div className="bb" style={{fontSize: '9.5px', lineHeight: 2}}>
              <span style={{color: '#ff69b4'}}>①</span> type ur mood<br/>
              <span style={{color: '#ff69b4'}}>②</span> pick ur vibe ♡<br/>
              <span style={{color: '#ff69b4'}}>③</span> press generate<br/>
              <span style={{color: '#ff69b4'}}>④</span> enjoy !!!! ✿
            </div>
          </div>

          <div className="lav-box">
            <div className="bh lav">✦ energy key</div>
            <div className="bb" style={{fontSize: '9.5px', lineHeight: 2.2}}>
              <span style={{color: '#87ceeb', fontWeight: 700}}>●</span> low = soft drift<br/>
              <span style={{color: '#ffd060', fontWeight: 700}}>●</span> medium = steady<br/>
              <span style={{color: '#ff6090', fontWeight: 700}}>●</span> high = full send
            </div>
          </div>

          <div className="dot-box" style={{borderColor: '#c490ff'}}>
            <div className="bh lav">★ ur playlist</div>
            <div className="bb" style={{fontSize: '9.5px', lineHeight: 1.9, fontFamily: "'Kosugi Maru',sans-serif"}}>
              <span style={{color: '#a06080'}}>name:</span><br/>
              <span style={{color: '#cc0066', fontSize: '9px'}}>{currentPlaylist?.playlist_name || '—'}</span><br/>
              <span style={{color: '#a06080'}}>songs:</span> <span style={{color: '#ff69b4', fontWeight: 700}}>{currentPlaylist?.songs?.length || 0}</span><br/>
              <span style={{color: '#a06080'}}>tags:</span><br/>
              <div style={{fontSize: '8.5px', color: '#c490ff', lineHeight: 1.6}}>{(currentPlaylist?.tags || []).join(' ♡ ') || '—'}</div>
            </div>
          </div>

          <div className="dot-box">
            <div className="bh pink">saved mixes</div>
            <div className="bb" style={{fontFamily: "'Kosugi Maru',sans-serif", fontSize: '9px', lineHeight: 1.7}}>
              {!session ? 'log in to see ur saved playlists' : playlists.length === 0 ? 'no saved playlists yet' : 
                playlists.map(pl => (
                  <div key={pl.id} className="hist-item" onClick={() => setCurrentPlaylist(pl.playlist)}>
                    <div className="hist-name">{pl.playlist.playlist_name}</div>
                    <div className="hist-meta">{pl.intent} / {pl.energy}<br/>{new Date(pl.created_at).toLocaleDateString()}</div>
                  </div>
                ))
              }
            </div>
          </div>
        </div>
      </div>
      <div className="starrow"></div>
      <div className="footer">✿ moodwave ✿ made with ♥ ✿ best viewed with headphones on ✿ please leave a comment if u enjoy !! ✿</div>
    </>
  );
}

export default App;
