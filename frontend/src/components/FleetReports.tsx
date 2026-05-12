import { useState } from 'react'
import { motion } from 'framer-motion'
import { FileText, Download, Calendar, Loader2, Printer, BarChart3 } from 'lucide-react'

export default function FleetReports() {
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'monthly'>('weekly')
  const [loading, setLoading] = useState(false)
  const [reportHtml, setReportHtml] = useState<string | null>(null)
  const [summary, setSummary] = useState<any>(null)

  const generateReport = async () => {
    setLoading(true)
    try {
      const res = await fetch(`/api/reports/generate?period=${period}`)
      const data = await res.json()
      setReportHtml(data.html)
      setSummary(data.summary)
    } catch (e) {
      console.error('Failed to generate report:', e)
    } finally {
      setLoading(false)
    }
  }

  const printReport = () => {
    if (!reportHtml) return
    const w = window.open('', '_blank')
    if (w) {
      w.document.write(reportHtml)
      w.document.close()
      setTimeout(() => w.print(), 500)
    }
  }

  const downloadReport = () => {
    if (!reportHtml) return
    const blob = new Blob([reportHtml], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `fleetpulse-report-${period}-${new Date().toISOString().slice(0, 10)}.html`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-gray-900/50 dark:bg-gray-900/50 light:bg-white border border-gray-800/50 dark:border-gray-800/50 light:border-gray-200 rounded-xl p-6"
      >
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <FileText className="w-6 h-6 text-blue-400" />
            <div>
              <h2 className="text-xl font-bold">Fleet Reports</h2>
              <p className="text-sm text-gray-400">Generate professional PDF reports with fleet analytics</p>
            </div>
          </div>
        </div>

        {/* Period Selector */}
        <div className="flex flex-wrap gap-4 items-center mb-6">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-gray-400" />
            <span className="text-sm text-gray-400">Report Period:</span>
          </div>
          <div className="flex gap-2">
            {(['daily', 'weekly', 'monthly'] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  period === p
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-800/50 text-gray-400 hover:bg-gray-700/50 hover:text-white'
                }`}
              >
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </button>
            ))}
          </div>
          <button
            onClick={generateReport}
            disabled={loading}
            className="ml-auto flex items-center gap-2 px-6 py-2 bg-gradient-to-r from-blue-500 to-purple-500 text-white rounded-lg font-medium hover:from-blue-600 hover:to-purple-600 disabled:opacity-50 transition-all"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <BarChart3 className="w-4 h-4" />}
            {loading ? 'Generating...' : 'Generate Report'}
          </button>
        </div>

        {/* Summary Cards */}
        {summary && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6"
          >
            <div className="bg-gray-800/30 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-blue-400">{summary.total_vehicles || 0}</div>
              <div className="text-xs text-gray-500 uppercase">Vehicles</div>
            </div>
            <div className="bg-gray-800/30 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-emerald-400">{summary.total_trips || 0}</div>
              <div className="text-xs text-gray-500 uppercase">Trips</div>
            </div>
            <div className="bg-gray-800/30 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-purple-400">{(summary.total_distance_mi || 0).toLocaleString(undefined, {maximumFractionDigits: 0})}</div>
              <div className="text-xs text-gray-500 uppercase">Miles</div>
            </div>
            <div className="bg-gray-800/30 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-amber-400">{summary.total_exceptions || 0}</div>
              <div className="text-xs text-gray-500 uppercase">Exceptions</div>
            </div>
            <div className="bg-gray-800/30 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-cyan-400">{summary.trailer_custody_inferred || 0}</div>
              <div className="text-xs text-gray-500 uppercase">Trailer Custody</div>
            </div>
          </motion.div>
        )}

        {/* Action Buttons */}
        {reportHtml && (
          <div className="flex gap-3 mb-6">
            <button
              onClick={printReport}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800/50 text-white rounded-lg hover:bg-gray-700/50 transition-all"
            >
              <Printer className="w-4 h-4" />
              Print / Save as PDF
            </button>
            <button
              onClick={downloadReport}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800/50 text-white rounded-lg hover:bg-gray-700/50 transition-all"
            >
              <Download className="w-4 h-4" />
              Download HTML
            </button>
          </div>
        )}

        {/* Report Preview */}
        {reportHtml && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white rounded-xl overflow-hidden shadow-2xl"
          >
            <iframe
              srcDoc={reportHtml}
              className="w-full border-0"
              style={{ height: '800px' }}
              title="Fleet Report Preview"
            />
          </motion.div>
        )}

        {!reportHtml && !loading && (
          <div className="text-center py-20 text-gray-500">
            <FileText className="w-16 h-16 mx-auto mb-4 opacity-30" />
            <p className="text-lg">Select a period and generate your fleet report</p>
            <p className="text-sm mt-2">Reports include trip data, safety exceptions, and fleet utilization metrics</p>
          </div>
        )}
      </motion.div>
    </div>
  )
}
