FROM brokenspoke-analyzer:analyzer-app

USER root
# needed to install just since apt-get install just returns unable to locate package just
# https://docs.makedeb.org/prebuilt-mpr/getting-started/#setting-up-the-repository
RUN apt-get update \
    && apt-get install -y npm python3-poetry \
    && wget -qO - 'https://proget.makedeb.org/debian-feeds/prebuilt-mpr.pub' | gpg --dearmor | tee /usr/share/keyrings/prebuilt-mpr-archive-keyring.gpg 1> /dev/null \
    && echo "deb [arch=all,$(dpkg --print-architecture) signed-by=/usr/share/keyrings/prebuilt-mpr-archive-keyring.gpg] https://proget.makedeb.org prebuilt-mpr $(cat /etc/os-release | grep "^VERSION_CODENAME=" | cut -d'=' -f2)" | tee /etc/apt/sources.list.d/prebuilt-mpr.list \
    && apt-get update \
    && apt-get install -y just \
    && apt-get clean all
USER bna
