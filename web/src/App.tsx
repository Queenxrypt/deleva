import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Landing } from "./pages/Landing";
import { Docs } from "./pages/Docs";
import { AppShell } from "./components/AppShell";
import { Overview } from "./pages/Overview";
import { Positions } from "./pages/Positions";
import { Strategies } from "./pages/Strategies";
import { Activity } from "./pages/Activity";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/docs" element={<Docs />} />
        <Route path="/app" element={<AppShell />}>
          <Route index element={<Overview />} />
          <Route path="positions" element={<Positions />} />
          <Route path="strategies" element={<Strategies />} />
          <Route path="activity" element={<Activity />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
