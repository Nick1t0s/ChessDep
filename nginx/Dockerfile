FROM nginx:1.27-alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY conf/ /etc/nginx/chessdep/
COPY 40-chessdep-conf.sh /docker-entrypoint.d/40-chessdep-conf.sh
RUN chmod +x /docker-entrypoint.d/40-chessdep-conf.sh
