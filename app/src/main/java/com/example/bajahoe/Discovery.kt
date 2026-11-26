package com.example.bajahoe

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

data class FoundDevice(val serviceName: String, val host: String, val port: Int)

/** 같은 Wi-Fi 안의 바자회 기기를 mDNS(_bajahoe._tcp)로 찾는다 */
class DeviceDiscovery(context: Context) {

    private val nsd = context.applicationContext.getSystemService(Context.NSD_SERVICE) as NsdManager

    private val _found = MutableStateFlow<List<FoundDevice>>(emptyList())
    val found: StateFlow<List<FoundDevice>> = _found.asStateFlow()

    private val _searching = MutableStateFlow(false)
    val searching: StateFlow<Boolean> = _searching.asStateFlow()

    private var listener: NsdManager.DiscoveryListener? = null
    private val pending = ArrayDeque<NsdServiceInfo>()
    private var resolving = false

    fun start() {
        if (listener != null) return
        val l = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) {
                _searching.value = true
            }

            override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                enqueue(serviceInfo)
            }

            override fun onServiceLost(serviceInfo: NsdServiceInfo) {
                _found.update { list -> list.filterNot { it.serviceName == serviceInfo.serviceName } }
            }

            override fun onDiscoveryStopped(serviceType: String) {
                _searching.value = false
            }

            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                _searching.value = false
                listener = null
            }

            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
                _searching.value = false
            }
        }
        listener = l
        try {
            nsd.discoverServices(Protocol.SERVICE_TYPE, NsdManager.PROTOCOL_DNS_SD, l)
        } catch (e: Exception) {
            listener = null
            _searching.value = false
        }
    }

    fun stop() {
        val l = listener ?: return
        listener = null
        try {
            nsd.stopServiceDiscovery(l)
        } catch (_: Exception) {
        }
        _searching.value = false
    }

    private fun enqueue(info: NsdServiceInfo) {
        synchronized(this) {
            pending.addLast(info)
        }
        resolveNext()
    }

    // API 34부터 resolveService 대신 registerServiceInfoCallback 을 권장하지만,
    // minSdk 26 을 지원하기 위해 한 번에 하나씩 순서대로 resolve 한다.
    @Suppress("DEPRECATION")
    private fun resolveNext() {
        val next: NsdServiceInfo
        synchronized(this) {
            if (resolving || pending.isEmpty()) return
            resolving = true
            next = pending.removeFirst()
        }
        try {
            nsd.resolveService(next, object : NsdManager.ResolveListener {
                override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                    done()
                }

                override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                    val host = serviceInfo.host?.hostAddress
                    if (host != null) {
                        val device = FoundDevice(serviceInfo.serviceName, host, serviceInfo.port)
                        _found.update { list ->
                            list.filterNot { it.serviceName == device.serviceName } + device
                        }
                    }
                    done()
                }
            })
        } catch (e: Exception) {
            done()
        }
    }

    private fun done() {
        synchronized(this) { resolving = false }
        resolveNext()
    }
}
