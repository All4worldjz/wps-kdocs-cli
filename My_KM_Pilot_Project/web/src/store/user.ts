import { defineStore } from 'pinia';
import axios from '../utils/axios';

export interface UserInfo {
  userId: string;
  username: string;
  nickname: string;
  mobile: string;
  avatar: string;
  profession: string;
  role: string;
}

export interface TokenUsage {
  totalTokens: number;
  usedTokens: number;
  remainingTokens: number;
  expireAt: string;
}

export const useUserStore = defineStore('user', {
  state: () => ({
    userInfo: null as UserInfo | null,
    usage: null as TokenUsage | null,
    uiConfig: {
      primaryColor: '#5B6EF6',
      secondaryColor: '#7B5CF7',
      accentColor: '#4B6EE3',
      showWatermark: false
    },
    writingConfig: {
      uploadMaxSizeMb: 10,
      allowedUploadFormats: ['doc', 'docx', 'txt', 'md', 'wps'],
      defaultSpeechWordCount: 3000,
      defaultNoticeWordCount: 1000
    }
  }),
  actions: {
    async fetchUserInfo() {
      try {
        const res: any = await axios.get('/gdios/api/user/getMyInfo');
        if (res && res.data) {
          this.userInfo = res.data;
        }
      } catch (err) {
        console.error('Failed to fetch user info:', err);
      }
    },
    async fetchUsage() {
      try {
        const res: any = await axios.post('/gdios/api/service/userMembership/queryUsage');
        if (res && res.data) {
          this.usage = res.data;
        }
      } catch (err) {
        console.error('Failed to fetch usage:', err);
      }
    },
    async fetchConfig() {
      try {
        const resUi: any = await axios.get('/geekseek/aiwriter/common/getUiConfig');
        if (resUi && resUi.data) {
          this.uiConfig = { ...this.uiConfig, ...resUi.data };
        }
        const resWrite: any = await axios.get('/geekseek/aiwriter/common/getWritingConfig');
        if (resWrite && resWrite.data) {
          this.writingConfig = { ...this.writingConfig, ...resWrite.data };
        }
      } catch (err) {
        console.error('Failed to fetch config:', err);
      }
    }
  }
});
