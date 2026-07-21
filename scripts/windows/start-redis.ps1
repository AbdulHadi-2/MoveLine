$containerName = "moveline-redis"

$existing = docker ps -a --filter "name=$containerName" --format "{{.Names}}"
if ($existing -contains $containerName) {
    docker start $containerName
} else {
    docker run --name $containerName -p 6379:6379 -d redis:7
}
