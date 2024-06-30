#!/usr/bin/env kotlin

@file:DependsOn(
    "io.ktor:ktor-client-core-jvm:2.3.12",
    "io.ktor:ktor-client-cio-jvm:2.3.12")

import io.ktor.client.*
import java.io.File
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import kotlinx.coroutines.runBlocking

//curl -X POST     -F 'client_name=Test Application'       -F 'redirect_uris=urn:ietf:wg:oauth:2.0:oob'    -F 'scopes=read write push'     -F 'website=https://myapp.example'      https://techhub.social/api/v1/apps
//{"id":"351364","name":"Test Application","website":"https://myapp.example","redirect_uri":"urn:ietf:wg:oauth:2.0:oob","client_id":"{CLIENT_ID}","client_secret":"{CLIENT_SECRET}}","vapid_key":"VAPID_KEY"}

//https://techhub.social/oauth/authorize?response_type=code&client_id=_EX_Y_tq769EK8SwkisicBReSDtG3ggRdgHwEN52-Xw&redirect_uri=urn:ietf:wg:oauth:2.0:oob&scope=write+read

val baseUrl = "https://127.0.0.1"
val authorizationToken = "token"
val filePath = "/home/me/Downloads/mastodon_tags.txt"

println(authorizationToken)
println(baseUrl)

 // Replace with your CSV file path
val file = File(filePath)

file.forEachLine { line ->
    val endpoint = "$baseUrl/api/v1/tags/$line/follow"
    println(endpoint)
    val client = HttpClient()
    runBlocking {
        val response: HttpResponse = client.request(endpoint) {
            method = HttpMethod.Post
            headers {
                append(HttpHeaders.Authorization, "Bearer $authorizationToken")
            }
        }
        println(response.status)
        println(response)
        Thread.sleep(2000)
    }
}
